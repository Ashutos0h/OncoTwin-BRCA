"""Small API-key authorization layer for research deployments."""

import secrets
from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader


api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="OncoTwinApiKey",
    description="Reader or writer API key configured by the backend operator.",
    auto_error=False,
)


class Authorizer:
    def __init__(
        self,
        *,
        enabled: bool = False,
        reader_key: str | None = None,
        writer_key: str | None = None,
    ) -> None:
        self.enabled = enabled
        self.reader_key = reader_key
        self.writer_key = writer_key

    @staticmethod
    def _matches(value: str | None, expected: str | None) -> bool:
        return bool(value and expected and secrets.compare_digest(value, expected))

    def require_reader(
        self,
        api_key: Annotated[str | None, Security(api_key_header)] = None,
    ) -> None:
        if not self.enabled:
            return
        if self._matches(api_key, self.reader_key) or self._matches(
            api_key, self.writer_key
        ):
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid API key is required.",
        )

    def require_writer(
        self,
        api_key: Annotated[str | None, Security(api_key_header)] = None,
    ) -> None:
        if not self.enabled:
            return
        if self._matches(api_key, self.writer_key):
            return
        if self._matches(api_key, self.reader_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Writer access is required.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid API key is required.",
        )

