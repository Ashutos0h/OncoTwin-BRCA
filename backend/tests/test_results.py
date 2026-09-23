from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.models import FeatureSnapshot
from backend.app.results import (
    AuditNotFoundError,
    InMemoryPredictionAuditStore,
    PredictionNotFoundError,
)


def snapshot() -> FeatureSnapshot:
    return FeatureSnapshot(
        schema_version="0.1.0",
        twin_id="twin-1",
        snapshot_id="snapshot-1",
        state_version=2,
        created_at="2026-09-03T00:00:00Z",
        data_version="data-v1",
        feature_set_version="demo-0.1.0",
        features={"grade": 2},
        missing_fields=[],
    )


def test_mock_prediction_and_audit_are_saved_together():
    ids = iter(
        [
            UUID("00000000-0000-0000-0000-000000000001"),
            UUID("00000000-0000-0000-0000-000000000002"),
        ]
    )
    store = InMemoryPredictionAuditStore(
        clock=lambda: datetime(2026, 9, 4, tzinfo=timezone.utc),
        id_factory=lambda: next(ids),
    )
    prediction, audit = store.create(snapshot(), ["event-1", "event-2"])

    assert prediction.prediction_id == "prediction_00000000000000000000000000000001"
    assert audit.audit_id == "audit_00000000000000000000000000000002"
    assert prediction.audit_id == audit.audit_id
    assert audit.prediction_id == prediction.prediction_id
    assert audit.event_ids == ["event-1", "event-2"]
    assert store.get_prediction(prediction.prediction_id) == prediction
    assert store.get_audit(audit.audit_id) == audit


def test_unknown_result_ids_are_rejected():
    store = InMemoryPredictionAuditStore()
    with pytest.raises(PredictionNotFoundError):
        store.get_prediction("missing")
    with pytest.raises(AuditNotFoundError):
        store.get_audit("missing")


def test_naive_prediction_clock_is_rejected_before_inference():
    store = InMemoryPredictionAuditStore(clock=lambda: datetime(2026, 9, 4))
    with pytest.raises(ValueError, match="timezone-aware"):
        store.create(snapshot(), ["event-1"])


def test_invalid_inference_output_is_not_persisted():
    class InvalidInference:
        def predict(self, snapshot, **kwargs):
            return {"unexpected": "output"}

    store = InMemoryPredictionAuditStore(inference=InvalidInference())
    with pytest.raises(ValidationError):
        store.create(snapshot(), ["event-1"])
    assert store.list_predictions("twin-1", limit=10, offset=0) == ([], 0)
    assert store.list_audits("twin-1", limit=10, offset=0) == ([], 0)
