"""Constant synthetic response for integration only; no trained inference.

This module implements the FeatureSnapshot -> Prediction boundary for
Milestone 1. It returns a fixed, schema-valid mock prediction that preserves
the lineage fields of the incoming snapshot.

Explicitly NOT implemented at this stage:
- real model training or inference
- probability calibration
- SHAP feature attribution
- out-of-distribution detection
- confidence estimation

Every output is a mock and must remain clearly labelled as such
(is_mock=True, confidence="not_assessed", ood_flag=None, shap_values=[]).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.validate_contracts import load_example, validate


MOCK_MODEL_NAME = "oncotwin-brca-mock"
MOCK_MODEL_VERSION = "0.0.0-mock"
MOCK_WARNING = (
    "Mock prediction: no trained model, calibration, SHAP, "
    "OOD or confidence assessment is available."
)

LINEAGE_FIELDS = ("twin_id", "snapshot_id", "state_version", "data_version")


def predict_demo(
    snapshot: Mapping[str, Any],
    *,
    prediction_id: str,
    audit_id: str,
    created_at: str,
) -> dict[str, Any]:
    """Return a schema-valid mock Prediction for the given FeatureSnapshot.

    The returned dict preserves the snapshot's lineage fields and explicitly
    flags itself as a mock. It must not be treated as a clinical result.
    """
    validate("feature-snapshot", snapshot)

    result = load_example("prediction")

    # Preserve lineage from the snapshot.
    for key in LINEAGE_FIELDS:
        result[key] = snapshot[key]

    # Force explicit mock indicators. These are never caller-controlled.
    result.update(
        prediction_id=prediction_id,
        audit_id=audit_id,
        created_at=created_at,
        model_name=MOCK_MODEL_NAME,
        model_version=MOCK_MODEL_VERSION,
        is_mock=True,
        confidence="not_assessed",
        ood_flag=None,
        shap_values=[],
    )

    # Surface the mock status as a warning, without duplicating.
    warnings = list(result.get("warnings") or [])
    if MOCK_WARNING not in warnings:
        warnings.append(MOCK_WARNING)
    result["warnings"] = warnings

    validate("prediction", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    result = predict_demo(
        json.loads(args.snapshot.read_text()),
        prediction_id="pred_demo_001",
        audit_id="audit_demo_001",
        created_at="2026-09-01T10:00:00Z",
    )
    print(json.dumps(result, indent=2))