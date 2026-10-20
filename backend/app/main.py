from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Response, Security, status
from fastapi.middleware.cors import CORSMiddleware

from backend.app.auth import Authorizer
from backend.app.config import Settings
from backend.app.inference import InferenceEngine, get_inference_engine
from backend.app.models import (
    AuditRecord,
    ClinicalEvent,
    ErrorResponse,
    EventAccepted,
    FeatureSnapshot,
    Page,
    Prediction,
    TwinCreate,
    TwinCreated,
    TwinState,
    TwinSummary,
)
from backend.app.observability import add_request_observability, configure_logging
from backend.app.ports import EventStore, PredictionAuditStore, SnapshotStore
from backend.app.results import (
    AuditNotFoundError,
    InMemoryPredictionAuditStore,
    PredictionNotFoundError,
)
from backend.app.snapshots import InMemorySnapshotStore, SnapshotNotFoundError
from backend.app.store import (
    DuplicateEventError,
    EmptyTwinError,
    InMemoryEventStore,
    InvalidQualityEventError,
    StateVersionConflictError,
    StorageUnavailableError,
    TwinAlreadyExistsError,
    TwinNotFoundError,
)


def create_app(
    store: EventStore | None = None,
    snapshot_store: SnapshotStore | None = None,
    result_store: PredictionAuditStore | None = None,
    *,
    storage_mode: str = "in-memory",
    cors_origins: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:5173"),
    auth_enabled: bool = False,
    reader_api_key: str | None = None,
    writer_api_key: str | None = None,
    log_level: str = "INFO",
    ml_inference_mode: str = "mock",
    inference: InferenceEngine | None = None,
) -> FastAPI:
    configure_logging(log_level)
    application = FastAPI(
        title="OncoTwin-BRCA research API",
        version="0.1.0",
        description="Research-only synthetic starter API; no clinical use.",
        openapi_tags=[
            {"name": "system", "description": "Process and storage health."},
            {"name": "twins", "description": "Twin lifecycle and reconstructed state."},
            {"name": "events", "description": "Immutable clinical event ingestion and history."},
            {"name": "snapshots", "description": "Versioned feature inputs for inference."},
            {"name": "predictions", "description": "Mock prediction creation and retrieval."},
            {"name": "audits", "description": "Prediction lineage and audit retrieval."},
        ],
    )
    engine = inference or get_inference_engine(ml_inference_mode)
    event_store = store or InMemoryEventStore()
    feature_snapshots = snapshot_store or InMemorySnapshotStore()
    prediction_results = result_store or InMemoryPredictionAuditStore(inference=engine)
    authorizer = Authorizer(
        enabled=auth_enabled,
        reader_key=reader_api_key,
        writer_key=writer_api_key,
    )
    reader_access = [Security(authorizer.require_reader)]
    writer_access = [Security(authorizer.require_writer)]
    add_request_observability(application)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "X-API-Key", "X-Request-ID"],
    )

    def require_twin(twin_id: str) -> None:
        try:
            event_store.events_for(twin_id)
        except TwinNotFoundError:
            raise HTTPException(status_code=404, detail="Twin not found.") from None

    @application.get("/health", tags=["system"])
    def health():
        return {"status": "ok", "service": "oncotwin-backend", "mode": storage_mode}

    @application.get("/api/v1/model/info", tags=["predictions"], dependencies=reader_access)
    def model_info():
        from pathlib import Path
        import json as _json
        meta_file = Path(__file__).resolve().parents[2] / "ml" / "models" / "model_metadata.json"
        if meta_file.exists():
            try:
                return _json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "model_name": "constant-demo",
            "model_version": "mock-0.1.0",
            "is_mock": True,
            "status": "mock_fallback",
        }

    @application.get(
        "/ready",
        tags=["system"],
        responses={503: {"model": ErrorResponse, "description": "Storage unavailable."}},
    )
    def ready():
        try:
            event_store.check_ready()
        except StorageUnavailableError:
            raise HTTPException(status_code=503, detail="Storage unavailable.") from None
        return {"status": "ready", "storage": storage_mode}

    @application.post(
        "/api/v1/twins",
        tags=["twins"],
        response_model=TwinCreated,
        status_code=status.HTTP_201_CREATED,
        responses={409: {"model": ErrorResponse, "description": "Twin already exists."}},
        dependencies=writer_access,
    )
    def create_twin(command: TwinCreate) -> TwinCreated:
        try:
            event_store.create_twin(command.twin_id)
        except TwinAlreadyExistsError:
            raise HTTPException(status_code=409, detail="Twin already exists.") from None
        return TwinCreated(twin_id=command.twin_id)

    @application.get(
        "/api/v1/twins",
        tags=["twins"],
        response_model=Page[TwinSummary],
        dependencies=reader_access,
    )
    def list_twins(
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Page[TwinSummary]:
        items, total = event_store.list_twins(limit=limit, offset=offset)
        return Page(items=items, total=total, limit=limit, offset=offset)

    @application.post(
        "/api/v1/twins/{twin_id}/events",
        tags=["events"],
        response_model=EventAccepted,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse, "description": "Twin not found."},
            409: {"model": ErrorResponse, "description": "Event ID already exists."},
            412: {"model": ErrorResponse, "description": "State version is stale."},
        },
        dependencies=writer_access,
    )
    def append_event(
        twin_id: str,
        event: ClinicalEvent,
        expected_state_version: Annotated[int | None, Query(ge=0)] = None,
    ) -> EventAccepted:
        if event.twin_id != twin_id:
            raise HTTPException(
                status_code=422,
                detail="Path twin_id must match the event twin_id.",
            )
        try:
            state_version = event_store.append(
                twin_id,
                event,
                expected_state_version=expected_state_version,
            )
        except TwinNotFoundError:
            raise HTTPException(status_code=404, detail="Twin not found.") from None
        except DuplicateEventError:
            raise HTTPException(status_code=409, detail="Event ID already exists.") from None
        except InvalidQualityEventError:
            raise HTTPException(
                status_code=422,
                detail="Events with invalid quality status are not accepted.",
            ) from None
        except StateVersionConflictError as error:
            raise HTTPException(
                status_code=412,
                detail=f"State version conflict. Current version is {error.current_version}.",
            ) from None
        return EventAccepted(
            twin_id=twin_id,
            event_id=event.event_id,
            state_version=state_version,
        )

    @application.get(
        "/api/v1/twins/{twin_id}/events",
        tags=["events"],
        response_model=Page[ClinicalEvent],
        responses={404: {"model": ErrorResponse, "description": "Twin not found."}},
        dependencies=reader_access,
    )
    def list_events(
        twin_id: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Page[ClinicalEvent]:
        try:
            items, total = event_store.list_for(twin_id, limit=limit, offset=offset)
        except TwinNotFoundError:
            raise HTTPException(status_code=404, detail="Twin not found.") from None
        return Page(items=items, total=total, limit=limit, offset=offset)

    @application.get(
        "/api/v1/twins/{twin_id}/state",
        tags=["twins"],
        response_model=TwinState,
        responses={
            404: {"model": ErrorResponse, "description": "Twin not found."},
            409: {"model": ErrorResponse, "description": "Twin has no accepted events."},
        },
        dependencies=reader_access,
    )
    def get_state(twin_id: str, response: Response) -> TwinState:
        try:
            state = event_store.rebuild(twin_id)
        except TwinNotFoundError:
            raise HTTPException(status_code=404, detail="Twin not found.") from None
        except EmptyTwinError:
            raise HTTPException(status_code=409, detail="Twin has no accepted events.") from None
        response.headers["ETag"] = f'"{state.state_version}"'
        return state

    @application.post(
        "/api/v1/twins/{twin_id}/snapshots",
        tags=["snapshots"],
        response_model=FeatureSnapshot,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse, "description": "Twin not found."},
            409: {"model": ErrorResponse, "description": "Twin has no accepted events."},
        },
        dependencies=writer_access,
    )
    def create_feature_snapshot(twin_id: str) -> FeatureSnapshot:
        try:
            state = event_store.rebuild(twin_id)
        except TwinNotFoundError:
            raise HTTPException(status_code=404, detail="Twin not found.") from None
        except EmptyTwinError:
            raise HTTPException(status_code=409, detail="Twin has no accepted events.") from None
        return feature_snapshots.create(state)

    @application.get(
        "/api/v1/twins/{twin_id}/snapshots",
        tags=["snapshots"],
        response_model=Page[FeatureSnapshot],
        responses={404: {"model": ErrorResponse, "description": "Twin not found."}},
        dependencies=reader_access,
    )
    def list_feature_snapshots(
        twin_id: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Page[FeatureSnapshot]:
        require_twin(twin_id)
        items, total = feature_snapshots.list_for(twin_id, limit=limit, offset=offset)
        return Page(items=items, total=total, limit=limit, offset=offset)

    @application.post(
        "/api/v1/twins/{twin_id}/snapshots/{snapshot_id}/predictions",
        tags=["predictions"],
        response_model=Prediction,
        status_code=status.HTTP_201_CREATED,
        responses={
            404: {"model": ErrorResponse, "description": "Snapshot not found for twin."},
        },
        dependencies=writer_access,
    )
    def create_prediction(twin_id: str, snapshot_id: str) -> Prediction:
        try:
            snapshot = feature_snapshots.get(snapshot_id)
            event_ids = feature_snapshots.event_ids_for(snapshot_id)
        except SnapshotNotFoundError:
            raise HTTPException(status_code=404, detail="Snapshot not found for twin.") from None
        if snapshot.twin_id != twin_id:
            raise HTTPException(status_code=404, detail="Snapshot not found for twin.")
        prediction, _audit = prediction_results.create(snapshot, event_ids)
        return prediction

    @application.get(
        "/api/v1/predictions/{prediction_id}",
        tags=["predictions"],
        response_model=Prediction,
        responses={404: {"model": ErrorResponse, "description": "Prediction not found."}},
        dependencies=reader_access,
    )
    def get_prediction(prediction_id: str) -> Prediction:
        try:
            return prediction_results.get_prediction(prediction_id)
        except PredictionNotFoundError:
            raise HTTPException(status_code=404, detail="Prediction not found.") from None

    @application.get(
        "/api/v1/twins/{twin_id}/predictions",
        tags=["predictions"],
        response_model=Page[Prediction],
        responses={404: {"model": ErrorResponse, "description": "Twin not found."}},
        dependencies=reader_access,
    )
    def list_predictions(
        twin_id: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Page[Prediction]:
        require_twin(twin_id)
        items, total = prediction_results.list_predictions(
            twin_id, limit=limit, offset=offset
        )
        return Page(items=items, total=total, limit=limit, offset=offset)

    @application.get(
        "/api/v1/audits/{audit_id}",
        tags=["audits"],
        response_model=AuditRecord,
        responses={404: {"model": ErrorResponse, "description": "Audit record not found."}},
        dependencies=reader_access,
    )
    def get_audit(audit_id: str) -> AuditRecord:
        try:
            return prediction_results.get_audit(audit_id)
        except AuditNotFoundError:
            raise HTTPException(status_code=404, detail="Audit record not found.") from None

    @application.get(
        "/api/v1/twins/{twin_id}/audits",
        tags=["audits"],
        response_model=Page[AuditRecord],
        responses={404: {"model": ErrorResponse, "description": "Twin not found."}},
        dependencies=reader_access,
    )
    def list_audits(
        twin_id: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> Page[AuditRecord]:
        require_twin(twin_id)
        items, total = prediction_results.list_audits(twin_id, limit=limit, offset=offset)
        return Page(items=items, total=total, limit=limit, offset=offset)

    application.state.event_store = event_store
    application.state.snapshot_store = feature_snapshots
    application.state.result_store = prediction_results
    return application


def create_configured_app() -> FastAPI:
    settings = Settings.from_env()
    inference = get_inference_engine(settings.ml_inference_mode)
    common = {
        "cors_origins": settings.cors_origins,
        "auth_enabled": settings.auth_enabled,
        "reader_api_key": settings.reader_api_key,
        "writer_api_key": settings.writer_api_key,
        "log_level": settings.log_level,
        "ml_inference_mode": settings.ml_inference_mode,
        "inference": inference,
    }
    if not settings.database_url:
        return create_app(**common)

    from backend.app.database import create_database_stores

    event_store, snapshot_store, result_store = create_database_stores(
        settings.database_url,
        inference=inference,
    )
    return create_app(
        event_store,
        snapshot_store,
        result_store,
        storage_mode="database",
        **common,
    )


app = create_configured_app()
