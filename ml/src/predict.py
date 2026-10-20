"""
Inference boundary for OncoTwin-BRCA ML module.

This module maps a validated FeatureSnapshot to a Prediction dict conforming
to contracts/prediction.schema.json v0.1.0.

Mock Boundary & Provenance
--------------------------
- `predict_demo(..., use_model=False)`: Explicit synthetic mock prediction.
  Always returns `is_mock=True`, `confidence="not_assessed"`, `ood_flag=None`,
  and an explicit mock warning.
- `predict_model(...)` or `predict_demo(..., use_model=True)`: Trained model inference.
  Loads calibrated model from ml/models/model.pkl and metadata from model_metadata.json.
  Returns `is_mock=False` with calibrated probability and rule-based OOD assessment.
- SHAP values explain model BEHAVIOUR only — not clinical causality.
- No diagnosis or treatment recommendations may be added.

Contract Conformance
--------------------
Every return value is validated against contracts/prediction.schema.json before
being returned. Any result failing schema validation raises ValidationError.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

try:
    import joblib
except ImportError:
    joblib = None

from scripts.validate_contracts import load_example, validate
from ml.src.preprocess import extract_features, ood_check, FEATURE_SET_VERSION

MODEL_PATH = Path(__file__).parent.parent / "models" / "model.pkl"
METADATA_PATH = Path(__file__).parent.parent / "models" / "model_metadata.json"

# Fixed mock values — clearly labelled synthetic; never change without bumping mock version
_MOCK_RISK = 0.31
_MOCK_MODEL_NAME = "constant-demo"
_MOCK_MODEL_VERSION = "mock-0.1.0"
_MOCK_WARNING = (
    "Synthetic mock output; no trained model, calibration, SHAP, or clinical interpretation."
)

_CONFIDENCE_THRESHOLDS = (0.35, 0.65)  # (low_upper, high_lower)


def _confidence_from_risk(risk: float, is_ood: bool) -> str:
    """Map calibrated risk score to confidence label. OOD always forces 'low'."""
    if is_ood:
        return "low"
    lo, hi = _CONFIDENCE_THRESHOLDS
    if risk <= lo or risk >= hi:
        return "high"
    return "moderate"


def _load_model_and_metadata() -> tuple | None:
    """
    Attempt to load trained model and its metadata.
    Returns (model, metadata_dict) or None if unavailable.
    """
    if joblib is None or np is None:
        return None
    if not MODEL_PATH.exists() or not METADATA_PATH.exists():
        return None
    try:
        model = joblib.load(MODEL_PATH)
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        return model, metadata
    except Exception:
        return None


def predict_demo(
    snapshot: dict,
    *,
    prediction_id: str,
    audit_id: str,
    created_at: str,
    use_model: bool = False,
) -> dict:
    """
    Map a validated FeatureSnapshot to a Prediction conforming to
    contracts/prediction.schema.json v0.1.0.

    Parameters
    ----------
    snapshot : dict
        A parsed FeatureSnapshot dict (must pass contracts/feature-snapshot.schema.json).
    prediction_id : str
        Unique ID for this prediction (supplied by Backend; globally unique).
    audit_id : str
        Audit record ID (reserved by Backend before calling; enables linkage).
    created_at : str
        RFC3339 timestamp for when this prediction was created (supplied by Backend).
    use_model : bool, default=False
        If False (default), returns the explicit deterministic mock prediction.
        If True, attempts real calibrated model inference from ml/models/model.pkl.

    Returns
    -------
    dict
        A Prediction dict conforming to contracts/prediction.schema.json.

    Raises
    ------
    jsonschema.ValidationError
        If the snapshot is malformed, or the generated prediction fails schema validation.
    """
    validate("feature-snapshot", snapshot)

    features_dict = snapshot.get("features", {})
    is_ood, ood_reasons = ood_check(features_dict)

    # Base dictionary seeded from contract fixture to ensure required structure
    result = load_example("prediction")

    # Propagate lineage fields from snapshot
    for field in ("twin_id", "snapshot_id", "state_version", "data_version"):
        result[field] = snapshot[field]
    result["prediction_id"] = prediction_id
    result["audit_id"] = audit_id
    result["created_at"] = created_at
    result["horizon_months"] = 60

    if use_model:
        loaded = _load_model_and_metadata()
        if loaded is not None and np is not None:
            model, metadata = loaded
            try:
                x = extract_features(features_dict)
                probs = model.predict_proba(x)
                risk = float(probs[0, 1])

                result["is_mock"] = False
                result["model_name"] = metadata.get("model_name", type(model).__name__)
                result["model_version"] = metadata.get("model_version", "unknown")
                result["risk_probability"] = risk
                result["ood_flag"] = is_ood
                result["confidence"] = _confidence_from_risk(risk, is_ood)

                warnings: list[str] = [
                    "Synthetic research prototype — not for clinical use."
                ]
                if is_ood:
                    warnings.extend(ood_reasons)
                if snapshot.get("missing_fields"):
                    warnings.append(
                        f"Missing features imputed with defaults: {snapshot['missing_fields']}"
                    )
                result["warnings"] = list(dict.fromkeys(warnings))
                result["shap_values"] = []
                validate("prediction", result)
                return result
            except Exception as exc:
                _fill_mock(result, is_ood, extra_warning=f"Inference fallback: {exc}")
        else:
            _fill_mock(result, is_ood, extra_warning="Trained model unavailable; using mock fallback.")
    else:
        _fill_mock(result, is_ood)

    validate("prediction", result)
    return result


def predict_model(
    snapshot: dict,
    *,
    prediction_id: str,
    audit_id: str,
    created_at: str,
) -> dict:
    """
    Convenience entrypoint for real trained model inference.
    Equivalent to `predict_demo(..., use_model=True)`.
    """
    return predict_demo(
        snapshot,
        prediction_id=prediction_id,
        audit_id=audit_id,
        created_at=created_at,
        use_model=True,
    )


def _fill_mock(result: dict, is_ood: bool, extra_warning: str | None = None) -> None:
    """Fill prediction dict with explicit mock values."""
    result["is_mock"] = True
    result["model_name"] = _MOCK_MODEL_NAME
    result["model_version"] = _MOCK_MODEL_VERSION
    result["risk_probability"] = _MOCK_RISK
    result["ood_flag"] = None
    result["confidence"] = "not_assessed"
    result["shap_values"] = []
    warnings = [_MOCK_WARNING]
    if extra_warning:
        warnings.append(extra_warning)
    result["warnings"] = warnings


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run mock or trained inference on a FeatureSnapshot JSON file."
    )
    parser.add_argument("snapshot", type=Path, help="Path to a FeatureSnapshot JSON file.")
    parser.add_argument("--prediction-id", default="pred_demo_001")
    parser.add_argument("--audit-id", default="audit_demo_001")
    parser.add_argument("--created-at", default="2026-09-01T10:00:00Z")
    parser.add_argument("--use-model", action="store_true", help="Use trained model instead of mock.")
    args = parser.parse_args()

    snap = json.loads(args.snapshot.read_text(encoding="utf-8"))
    pred = predict_demo(
        snap,
        prediction_id=args.prediction_id,
        audit_id=args.audit_id,
        created_at=args.created_at,
        use_model=args.use_model,
    )
    print(json.dumps(pred, indent=2))
