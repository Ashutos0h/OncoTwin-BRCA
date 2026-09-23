"""Mock inference integration with atomic prediction/audit persistence."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from threading import RLock
from uuid import UUID, uuid4

from backend.app.inference import InferenceEngine, MockInferenceEngine
from backend.app.models import AuditRecord, FeatureSnapshot, Prediction


class AuditNotFoundError(Exception):
    pass


class PredictionNotFoundError(Exception):
    pass


class InMemoryPredictionAuditStore:
    """Create a mock prediction and save it with its audit in one critical section."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], UUID] | None = None,
        inference: InferenceEngine | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or uuid4
        self._inference = inference or MockInferenceEngine()
        self._predictions: dict[str, str] = {}
        self._audits: dict[str, str] = {}
        self._lock = RLock()

    def create(
        self,
        snapshot: FeatureSnapshot,
        event_ids: Sequence[str],
    ) -> tuple[Prediction, AuditRecord]:
        created_at = self._clock()
        if created_at.utcoffset() is None:
            raise ValueError("Prediction clock must return a timezone-aware datetime.")

        prediction_id = f"prediction_{self._id_factory().hex}"
        audit_id = f"audit_{self._id_factory().hex}"
        timestamp = created_at.isoformat().replace("+00:00", "Z")
        prediction = Prediction.model_validate(
            self._inference.predict(
                snapshot,
                prediction_id=prediction_id,
                audit_id=audit_id,
                created_at=timestamp,
            )
        )
        audit = AuditRecord(
            schema_version="0.1.0",
            twin_id=snapshot.twin_id,
            audit_id=audit_id,
            recorded_at=created_at,
            action="PREDICTION_CREATED",
            actor="oncotwin-backend",
            event_ids=list(event_ids),
            state_version=snapshot.state_version,
            snapshot_id=snapshot.snapshot_id,
            prediction_id=prediction.prediction_id,
            model_version=prediction.model_version,
            data_version=snapshot.data_version,
        )

        prediction_json = prediction.model_dump_json()
        audit_json = audit.model_dump_json()
        with self._lock:
            self._predictions[prediction.prediction_id] = prediction_json
            self._audits[audit.audit_id] = audit_json
        return (
            Prediction.model_validate_json(prediction_json),
            AuditRecord.model_validate_json(audit_json),
        )

    def get_prediction(self, prediction_id: str) -> Prediction:
        with self._lock:
            try:
                value = self._predictions[prediction_id]
            except KeyError:
                raise PredictionNotFoundError(prediction_id) from None
        return Prediction.model_validate_json(value)

    def get_audit(self, audit_id: str) -> AuditRecord:
        with self._lock:
            try:
                value = self._audits[audit_id]
            except KeyError:
                raise AuditNotFoundError(audit_id) from None
        return AuditRecord.model_validate_json(value)

    def list_predictions(
        self, twin_id: str, *, limit: int, offset: int
    ) -> tuple[list[Prediction], int]:
        with self._lock:
            values = [Prediction.model_validate_json(value) for value in self._predictions.values()]
        matching = sorted(
            (item for item in values if item.twin_id == twin_id),
            key=lambda item: (item.created_at, item.prediction_id),
            reverse=True,
        )
        return matching[offset : offset + limit], len(matching)

    def list_audits(
        self, twin_id: str, *, limit: int, offset: int
    ) -> tuple[list[AuditRecord], int]:
        with self._lock:
            values = [AuditRecord.model_validate_json(value) for value in self._audits.values()]
        matching = sorted(
            (item for item in values if item.twin_id == twin_id),
            key=lambda item: (item.recorded_at, item.audit_id),
            reverse=True,
        )
        return matching[offset : offset + limit], len(matching)
