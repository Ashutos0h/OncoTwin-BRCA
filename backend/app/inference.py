"""Inference boundary used by persistence without coupling it to ML internals."""

from typing import Any, Protocol

from backend.app.models import FeatureSnapshot
from ml.src.predict import predict_demo


class InferenceEngine(Protocol):
    def predict(
        self,
        snapshot: FeatureSnapshot,
        *,
        prediction_id: str,
        audit_id: str,
        created_at: str,
    ) -> dict[str, Any]: ...


class MockInferenceEngine:
    """Adapter for the explicit, synthetic ML placeholder."""

    def predict(
        self,
        snapshot: FeatureSnapshot,
        *,
        prediction_id: str,
        audit_id: str,
        created_at: str,
    ) -> dict[str, Any]:
        return predict_demo(
            snapshot.model_dump(mode="json"),
            prediction_id=prediction_id,
            audit_id=audit_id,
            created_at=created_at,
        )

