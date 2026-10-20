"""
Comprehensive tests for ml.src.predict, ml.src.preprocess, and ml.src.train.

Coverage:
  - Mock boundary: always is_mock=True when no model file present
  - Real inference: is_mock=False when trained model is available
  - Determinism: identical input → identical output
  - Lineage: all snapshot fields propagate correctly to prediction
  - Contract: every output validates against contracts/prediction.schema.json
  - Feature preprocessing: encoding, imputation, OOD check
  - Training: patient-level split anti-leakage, model comparison, metadata
  - Schema rejection: malformed snapshots raise ValidationError
"""
import copy
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest
from jsonschema import ValidationError

from scripts.validate_contracts import load_example, validate
from ml.src.predict import predict_demo, predict_model
from ml.src.preprocess import (
    extract_features,
    ood_check,
    missing_mask,
    ALL_FEATURE_NAMES,
    FEATURE_SET_VERSION,
    IHC_ENCODING,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(**overrides) -> dict:
    snap = load_example("feature-snapshot")
    snap.update(overrides)
    return snap


PRED_KWARGS = dict(
    prediction_id="pred_test_001",
    audit_id="audit_test_001",
    created_at="2026-09-01T10:00:00Z",
)


# ---------------------------------------------------------------------------
# Mock Boundary (no model on disk)
# ---------------------------------------------------------------------------

class TestMockBoundary:
    """Tests that verify is_mock=True when no trained model is available."""

    def test_mock_is_explicit(self, monkeypatch):
        """When model file is absent, is_mock must be True."""
        monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
        monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
        snap = _make_snapshot()
        result = predict_demo(snap, **PRED_KWARGS)
        assert result["is_mock"] is True

    def test_mock_model_name_is_constant_demo(self, monkeypatch):
        monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
        monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
        result = predict_demo(_make_snapshot(), **PRED_KWARGS)
        assert result["model_name"] == "constant-demo"

    def test_mock_confidence_not_assessed(self, monkeypatch):
        monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
        monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
        result = predict_demo(_make_snapshot(), **PRED_KWARGS)
        assert result["confidence"] == "not_assessed"

    def test_mock_ood_flag_none(self, monkeypatch):
        monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
        monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
        result = predict_demo(_make_snapshot(), **PRED_KWARGS)
        assert result["ood_flag"] is None

    def test_mock_shap_values_empty(self, monkeypatch):
        monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
        monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
        result = predict_demo(_make_snapshot(), **PRED_KWARGS)
        assert result["shap_values"] == []

    def test_mock_warning_present(self, monkeypatch):
        monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
        monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
        result = predict_demo(_make_snapshot(), **PRED_KWARGS)
        assert len(result["warnings"]) >= 1
        assert any("mock" in w.lower() or "synthetic" in w.lower() for w in result["warnings"])

    def test_mock_risk_in_valid_range(self, monkeypatch):
        monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
        monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
        result = predict_demo(_make_snapshot(), **PRED_KWARGS)
        assert 0.0 <= result["risk_probability"] <= 1.0

    def test_mock_validates_contract(self, monkeypatch):
        monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
        monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
        result = predict_demo(_make_snapshot(), **PRED_KWARGS)
        validate("prediction", result)  # Must not raise


# ---------------------------------------------------------------------------
# Lineage & Determinism
# ---------------------------------------------------------------------------

class TestLineageAndDeterminism:

    def test_snapshot_fields_propagate(self, monkeypatch):
        monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
        monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
        snap = _make_snapshot(
            twin_id="TWIN_XYZ",
            snapshot_id="snap_abc",
            state_version=5,
            data_version="v2",
        )
        result = predict_demo(snap, **PRED_KWARGS)
        assert result["twin_id"] == "TWIN_XYZ"
        assert result["snapshot_id"] == "snap_abc"
        assert result["state_version"] == 5
        assert result["data_version"] == "v2"

    def test_prediction_id_propagates(self, monkeypatch):
        monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
        monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
        result = predict_demo(_make_snapshot(), **{**PRED_KWARGS, "prediction_id": "pred_unique"})
        assert result["prediction_id"] == "pred_unique"

    def test_audit_id_propagates(self, monkeypatch):
        monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
        monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
        result = predict_demo(_make_snapshot(), **{**PRED_KWARGS, "audit_id": "audit_xyz"})
        assert result["audit_id"] == "audit_xyz"

    def test_deterministic_mock(self, monkeypatch):
        monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
        monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
        snap = _make_snapshot()
        r1 = predict_demo(snap, **PRED_KWARGS)
        r2 = predict_demo(snap, **PRED_KWARGS)
        assert r1 == r2

    def test_snapshot_not_mutated(self, monkeypatch):
        monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
        monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
        snap = _make_snapshot()
        original = copy.deepcopy(snap)
        predict_demo(snap, **PRED_KWARGS)
        assert snap == original

    def test_horizon_months_is_60(self, monkeypatch):
        monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
        monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
        result = predict_demo(_make_snapshot(), **PRED_KWARGS)
        assert result["horizon_months"] == 60


# ---------------------------------------------------------------------------
# Schema Validation (rejection of invalid input)
# ---------------------------------------------------------------------------

class TestSchemaRejection:

    def test_empty_snapshot_rejected(self):
        with pytest.raises(ValidationError):
            predict_demo({}, **PRED_KWARGS)

    def test_missing_twin_id_rejected(self):
        snap = _make_snapshot()
        del snap["twin_id"]
        with pytest.raises(ValidationError):
            predict_demo(snap, **PRED_KWARGS)

    def test_missing_features_rejected(self):
        snap = _make_snapshot()
        del snap["features"]
        with pytest.raises(ValidationError):
            predict_demo(snap, **PRED_KWARGS)


# ---------------------------------------------------------------------------
# Real Model Inference (model.pkl present on disk)
# ---------------------------------------------------------------------------

class TestRealModelInference:
    """Tests against the trained model.pkl from ml/src/train.py."""

    MODEL_PATH = Path(__file__).parent.parent / "models" / "model.pkl"
    META_PATH = Path(__file__).parent.parent / "models" / "model_metadata.json"

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "models" / "model.pkl").exists(),
        reason="Trained model not found — run python -m ml.src.train first",
    )
    def test_real_inference_is_not_mock(self):
        snap = _make_snapshot()
        snap["features"] = {
            "tumour_size_mm": 31.0,
            "grade": 2,
            "positive_nodes": 3,
            "her2_status": "positive",
            "er_status": "positive",
            "pr_status": "negative",
            "ki67_percent": 25.0,
        }
        result = predict_model(snap, **PRED_KWARGS)
        assert result["is_mock"] is False

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "models" / "model.pkl").exists(),
        reason="Trained model not found",
    )
    def test_real_inference_validates_contract(self):
        snap = _make_snapshot()
        result = predict_model(snap, **PRED_KWARGS)
        validate("prediction", result)

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "models" / "model.pkl").exists(),
        reason="Trained model not found",
    )
    def test_real_inference_risk_in_range(self):
        snap = _make_snapshot()
        result = predict_model(snap, **PRED_KWARGS)
        assert 0.0 <= result["risk_probability"] <= 1.0

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "models" / "model.pkl").exists(),
        reason="Trained model not found",
    )
    def test_real_inference_ood_normal_input(self):
        snap = _make_snapshot()
        snap["features"]["tumour_size_mm"] = 25.0
        snap["features"]["positive_nodes"] = 2
        result = predict_model(snap, **PRED_KWARGS)
        assert result["ood_flag"] is False

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "models" / "model.pkl").exists(),
        reason="Trained model not found",
    )
    def test_real_inference_ood_extreme_size(self):
        snap = _make_snapshot()
        snap["features"]["tumour_size_mm"] = 150.0  # > 100 = OOD
        result = predict_model(snap, **PRED_KWARGS)
        assert result["ood_flag"] is True
        assert result["confidence"] == "low"

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "models" / "model.pkl").exists(),
        reason="Trained model not found",
    )
    def test_real_inference_deterministic(self):
        snap = _make_snapshot()
        r1 = predict_model(snap, **PRED_KWARGS)
        r2 = predict_model(snap, **PRED_KWARGS)
        assert r1["risk_probability"] == r2["risk_probability"]
        assert r1["confidence"] == r2["confidence"]


# ---------------------------------------------------------------------------
# Preprocessing — extract_features
# ---------------------------------------------------------------------------

class TestExtractFeatures:

    def test_output_shape(self):
        fd = {"tumour_size_mm": 25.0, "grade": 2, "positive_nodes": 3}
        x = extract_features(fd)
        assert x.shape == (1, len(ALL_FEATURE_NAMES))

    def test_dtype_float32(self):
        x = extract_features({"tumour_size_mm": 10.0})
        assert x.dtype == np.float32

    def test_numeric_values_correct(self):
        fd = {"tumour_size_mm": 31.0, "grade": 3, "positive_nodes": 5, "ki67_percent": 40.0}
        x = extract_features(fd)
        assert float(x[0, 0]) == pytest.approx(31.0)
        assert float(x[0, 1]) == pytest.approx(3.0)
        assert float(x[0, 2]) == pytest.approx(5.0)
        assert float(x[0, 3]) == pytest.approx(40.0)

    def test_ihc_encoding_positive(self):
        fd = {"her2_status": "positive", "er_status": "positive", "pr_status": "positive"}
        x = extract_features(fd)
        # her2 is at index 4, er at 5, pr at 6
        assert float(x[0, 4]) == pytest.approx(IHC_ENCODING["positive"])
        assert float(x[0, 5]) == pytest.approx(IHC_ENCODING["positive"])
        assert float(x[0, 6]) == pytest.approx(IHC_ENCODING["positive"])

    def test_ihc_encoding_negative(self):
        fd = {"her2_status": "negative", "er_status": "negative", "pr_status": "negative"}
        x = extract_features(fd)
        assert float(x[0, 4]) == pytest.approx(IHC_ENCODING["negative"])

    def test_ihc_encoding_equivocal(self):
        fd = {"her2_status": "equivocal"}
        x = extract_features(fd)
        assert float(x[0, 4]) == pytest.approx(IHC_ENCODING["equivocal"])

    def test_null_numeric_uses_default(self):
        from ml.src.preprocess import NUMERIC_FILL_DEFAULTS
        fd = {"tumour_size_mm": None}
        x = extract_features(fd)
        assert float(x[0, 0]) == pytest.approx(NUMERIC_FILL_DEFAULTS["tumour_size_mm"])

    def test_null_ihc_becomes_nan(self):
        fd = {"her2_status": None}
        x = extract_features(fd)
        assert np.isnan(x[0, 4])

    def test_empty_features_uses_all_defaults(self):
        x = extract_features({})
        assert x.shape == (1, len(ALL_FEATURE_NAMES))
        # All numeric fields should have fill defaults, IHC should be NaN
        assert not np.isnan(x[0, 0])  # tumour_size_mm filled


# ---------------------------------------------------------------------------
# OOD Detection
# ---------------------------------------------------------------------------

class TestOodCheck:

    def test_normal_inputs_not_ood(self):
        fd = {"tumour_size_mm": 30.0, "positive_nodes": 2, "grade": 2, "ki67_percent": 20.0}
        is_ood, reasons = ood_check(fd)
        assert not is_ood
        assert reasons == []

    def test_tumour_size_over_100_is_ood(self):
        fd = {"tumour_size_mm": 101.0}
        is_ood, reasons = ood_check(fd)
        assert is_ood
        assert any("tumour_size_mm" in r for r in reasons)

    def test_nodes_over_30_is_ood(self):
        fd = {"positive_nodes": 31}
        is_ood, reasons = ood_check(fd)
        assert is_ood
        assert any("positive_nodes" in r for r in reasons)

    def test_ki67_over_100_is_ood(self):
        fd = {"ki67_percent": 101.0}
        is_ood, reasons = ood_check(fd)
        assert is_ood

    def test_ki67_negative_is_ood(self):
        fd = {"ki67_percent": -1.0}
        is_ood, reasons = ood_check(fd)
        assert is_ood

    def test_multiple_ood_reasons(self):
        fd = {"tumour_size_mm": 200.0, "positive_nodes": 50}
        is_ood, reasons = ood_check(fd)
        assert is_ood
        assert len(reasons) >= 2

    def test_null_values_not_ood(self):
        fd = {"tumour_size_mm": None, "positive_nodes": None}
        is_ood, _ = ood_check(fd)
        assert not is_ood


# ---------------------------------------------------------------------------
# Missing Mask
# ---------------------------------------------------------------------------

class TestMissingMask:

    def test_no_missing(self):
        fd = {f: 1.0 for f in ALL_FEATURE_NAMES}
        assert missing_mask(fd) == []

    def test_detects_null_fields(self):
        fd = {"tumour_size_mm": None, "her2_status": None}
        missing = missing_mask(fd)
        assert "tumour_size_mm" in missing
        assert "her2_status" in missing

    def test_absent_key_treated_as_missing(self):
        missing = missing_mask({})
        assert set(missing) == set(ALL_FEATURE_NAMES)


# ---------------------------------------------------------------------------
# Training Pipeline (smoke test without full run)
# ---------------------------------------------------------------------------

class TestTrainingPipeline:

    def test_synthetic_cohort_generation(self):
        from ml.src.train import generate_synthetic_cohort
        df = generate_synthetic_cohort(n_patients=50, seed=0)
        assert len(df) == 50
        assert "recurrence_5yr" in df.columns
        assert set(df["recurrence_5yr"].unique()).issubset({0, 1})

    def test_synthetic_cohort_has_correct_features(self):
        from ml.src.train import generate_synthetic_cohort
        df = generate_synthetic_cohort(n_patients=20)
        for feat in ["tumour_size_mm", "grade", "positive_nodes", "ki67_percent",
                     "her2_status", "er_status", "pr_status"]:
            assert feat in df.columns

    def test_synthetic_cohort_deterministic(self):
        from ml.src.train import generate_synthetic_cohort
        df1 = generate_synthetic_cohort(n_patients=100, seed=99)
        df2 = generate_synthetic_cohort(n_patients=100, seed=99)
        assert (df1["tumour_size_mm"].values == df2["tumour_size_mm"].values).all()

    def test_train_runs_without_error(self):
        from ml.src.train import train
        meta = train(n_patients=120, seed=7, save=False)
        assert "model_name" in meta
        assert "test_roc_auc" in meta
        assert 0.0 <= meta["test_roc_auc"] <= 1.0
        assert 0.0 <= meta["test_brier_score"] <= 1.0

    def test_train_patient_level_no_leakage(self):
        from ml.src.train import generate_synthetic_cohort
        from data.src.etl import patient_level_train_test_split
        df = generate_synthetic_cohort(n_patients=100, seed=1)
        records = df.to_dict(orient="records")
        train_r, rest_r = patient_level_train_test_split(
            records, patient_id_key="twin_id", test_ratio=0.30, seed=1
        )
        val_r, test_r = patient_level_train_test_split(
            rest_r, patient_id_key="twin_id", test_ratio=0.50, seed=1
        )
        train_ids = {r["twin_id"] for r in train_r}
        val_ids = {r["twin_id"] for r in val_r}
        test_ids = {r["twin_id"] for r in test_r}
        assert not (train_ids & val_ids)
        assert not (train_ids & test_ids)
        assert not (val_ids & test_ids)

    def test_train_model_metadata_keys(self):
        from ml.src.train import train
        meta = train(n_patients=80, seed=5, save=False)
        required_keys = [
            "model_name", "model_version", "feature_set_version",
            "feature_names", "outcome_label", "horizon_months",
            "is_synthetic", "test_roc_auc", "test_brier_score",
            "candidates", "calibration", "ood_rules", "shap_note",
        ]
        for key in required_keys:
            assert key in meta, f"Missing metadata key: {key}"

    def test_train_candidate_comparison(self):
        from ml.src.train import train
        meta = train(n_patients=80, seed=3, save=False)
        assert "LogisticRegression" in meta["candidates"]
        assert "XGBClassifier" in meta["candidates"]
        for name, stats in meta["candidates"].items():
            assert 0.0 <= stats["val_roc_auc"] <= 1.0

    def test_feature_set_version_stable(self):
        assert FEATURE_SET_VERSION == "0.2.0"


# ---------------------------------------------------------------------------
# Contract round-trip (existing tests extended)
# ---------------------------------------------------------------------------

def test_mock_preserves_lineage_and_input(monkeypatch):
    """Original acceptance test — must remain green."""
    monkeypatch.setattr("ml.src.predict.MODEL_PATH", Path("/nonexistent/model.pkl"))
    monkeypatch.setattr("ml.src.predict.METADATA_PATH", Path("/nonexistent/meta.json"))
    snapshot = load_example("feature-snapshot")
    snapshot.update(
        twin_id="SYNTHETIC_OTHER",
        snapshot_id="snapshot_other",
        state_version=2,
        data_version="synthetic-2",
    )
    before = copy.deepcopy(snapshot)
    kwargs = dict(prediction_id="pred_other", audit_id="audit_other", created_at="2026-09-02T00:00:00Z")
    result = predict_demo(snapshot, **kwargs)
    validate("prediction", result)
    assert result == predict_demo(snapshot, **kwargs)
    assert snapshot == before
    for field in ("twin_id", "snapshot_id", "state_version", "data_version"):
        assert result[field] == snapshot[field]
    assert result["audit_id"] == "audit_other"
    assert result["is_mock"] is True
    assert result["confidence"] == "not_assessed"
    assert result["ood_flag"] is None


def test_invalid_input_rejected():
    """Original acceptance test — must remain green."""
    with pytest.raises(ValidationError):
        predict_demo({}, prediction_id="p", audit_id="a", created_at="2026-09-02T00:00:00Z")
