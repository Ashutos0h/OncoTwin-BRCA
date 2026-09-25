"""Contract and behaviour tests for the mock FeatureSnapshot -> Prediction boundary."""

from copy import deepcopy

import pytest
from jsonschema import ValidationError

from ml.src.predict import (
    LINEAGE_FIELDS,
    MOCK_MODEL_NAME,
    MOCK_MODEL_VERSION,
    MOCK_WARNING,
    predict_demo,
)
from scripts.validate_contracts import load_example, validate


def test_mock_preserves_lineage_and_input():
    snapshot = load_example("feature-snapshot")
    snapshot.update(
        twin_id="SYNTHETIC_OTHER",
        snapshot_id="snapshot_other",
        state_version=2,
        data_version="synthetic-2",
    )
    before = deepcopy(snapshot)
    kwargs = dict(
        prediction_id="pred_other",
        audit_id="audit_other",
        created_at="2026-09-02T00:00:00Z",
    )

    result = predict_demo(snapshot, **kwargs)
    validate("prediction", result)

    # Deterministic for the same input and IDs.
    assert result == predict_demo(snapshot, **kwargs)

    # Input is not mutated.
    assert snapshot == before

    # Lineage is preserved from the snapshot.
    for field in LINEAGE_FIELDS:
        assert result[field] == snapshot[field]

    # Caller-supplied identifiers are respected.
    assert result["audit_id"] == "audit_other"
    assert result["prediction_id"] == "pred_other"
    assert result["created_at"] == "2026-09-02T00:00:00Z"


def test_mock_indicators_are_explicit():
    snapshot = load_example("feature-snapshot")
    result = predict_demo(
        snapshot,
        prediction_id="pred_mock",
        audit_id="audit_mock",
        created_at="2026-09-02T00:00:00Z",
    )

    # Mock flags must never be faked.
    assert result["is_mock"] is True
    assert result["confidence"] == "not_assessed"
    assert result["ood_flag"] is None
    assert result["shap_values"] == []

    # Model identity is the mock, not a real registered model.
    assert result["model_name"] == MOCK_MODEL_NAME
    assert result["model_version"] == MOCK_MODEL_VERSION


def test_mock_emits_warning_and_is_idempotent():
    snapshot = load_example("feature-snapshot")
    kwargs = dict(
        prediction_id="pred_warn",
        audit_id="audit_warn",
        created_at="2026-09-02T00:00:00Z",
    )

    first = predict_demo(snapshot, **kwargs)
    assert MOCK_WARNING in first["warnings"]

    # Calling again must not duplicate the warning.
    second = predict_demo(snapshot, **kwargs)
    assert second["warnings"].count(MOCK_WARNING) == 1


def test_mock_output_passes_prediction_contract():
    snapshot = load_example("feature-snapshot")
    result = predict_demo(
        snapshot,
        prediction_id="pred_contract",
        audit_id="audit_contract",
        created_at="2026-09-02T00:00:00Z",
    )
    # validate() raises on failure; this asserts the full contract.
    validate("prediction", result)


def test_invalid_input_rejected():
    with pytest.raises(ValidationError):
        predict_demo(
            {},
            prediction_id="p",
            audit_id="a",
            created_at="2026-09-02T00:00:00Z",
        )


def test_snapshot_missing_feature_field_rejected():
    snapshot = load_example("feature-snapshot")
    snapshot.pop("features")
    with pytest.raises(ValidationError):
        predict_demo(
            snapshot,
            prediction_id="p",
            audit_id="a",
            created_at="2026-09-02T00:00:00Z",
        )


def test_risk_probability_stays_within_contract_bounds():
    snapshot = load_example("feature-snapshot")
    result = predict_demo(
        snapshot,
        prediction_id="pred_bounds",
        audit_id="audit_bounds",
        created_at="2026-09-02T00:00:00Z",
    )
    assert 0.0 <= result["risk_probability"] <= 1.0
    assert isinstance(result["horizon_months"], int)
    assert result["horizon_months"] >= 1