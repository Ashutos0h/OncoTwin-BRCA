"""Request correlation and privacy-conscious structured access logging."""

import json
import logging
import re
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request


REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level, logging.INFO))


def add_request_observability(application: FastAPI) -> None:
    logger = logging.getLogger("oncotwin.access")

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else uuid4().hex
        request.state.request_id = request_id
        started = perf_counter()
        response = await call_next(request)
        duration_ms = round((perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = str(duration_ms)
        route = request.scope.get("route")
        path_template = getattr(route, "path", request.url.path)
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": path_template,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
                separators=(",", ":"),
            )
        )
        return response
