"""
Preprocessing pipeline for OncoTwin-BRCA ML module.

Handles all 8 agreed features from the Data/FHIR feature dictionary:
  tumour_size_mm, grade, positive_nodes, her2_status,
  er_status, pr_status, ki67_percent, morphology_code

Anti-leakage guarantee: this module ONLY transforms features.
It never performs train/test splitting — that is the exclusive
responsibility of ml/src/train.py using patient-level splits.

SHAP explains model behaviour, not clinical causality.
No diagnosis or treatment recommendations may be added here.
"""
from __future__ import annotations

from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Agreed feature set order (must be stable — do not reorder without versioning)
# ---------------------------------------------------------------------------
NUMERIC_FEATURES = [
    "tumour_size_mm",   # float, ≥ 0
    "grade",            # int, 1–4
    "positive_nodes",   # int, ≥ 0
    "ki67_percent",     # float, 0–100 (nullable)
]

CATEGORICAL_FEATURES = [
    "her2_status",      # positive / negative / equivocal / null
    "er_status",        # positive / negative / null
    "pr_status",        # positive / negative / null
]

# morphology_code is excluded from model features (categorical with high cardinality,
# no agreed encoding; raise as contract proposal before including)
EXCLUDED_FEATURES = ["morphology_code"]

ALL_FEATURE_NAMES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Default fill values for imputation (median for numeric, mode constant for categorical)
NUMERIC_FILL_DEFAULTS: dict[str, float] = {
    "tumour_size_mm": 25.0,   # median-like placeholder
    "grade": 2.0,
    "positive_nodes": 0.0,
    "ki67_percent": 20.0,
}

# IHC categorical encoding (ordinal risk ordering based on known biology)
# Not a clinical recommendation — for synthetic model exploration only
IHC_ENCODING: dict[str, float] = {
    "negative": 0.0,
    "equivocal": 0.5,
    "positive": 1.0,
}

FEATURE_SET_VERSION = "0.2.0"  # Bump whenever FEATURE_NAMES or encoding changes


def extract_features(features_dict: dict[str, Any]) -> np.ndarray:
    """
    Extract and encode feature values from a FeatureSnapshot.features dict
    into a fixed-length float32 numpy array suitable for scikit-learn / XGBoost.

    Missing/null values are filled with agreed defaults (imputation).
    Categorical IHC fields are encoded as ordered numerics.

    Parameters
    ----------
    features_dict : dict
        The 'features' sub-dict from a FeatureSnapshot, as produced by the backend.

    Returns
    -------
    np.ndarray
        Shape (1, len(ALL_FEATURE_NAMES)) float32 array.
    """
    row: list[float] = []

    for feat in NUMERIC_FEATURES:
        val = features_dict.get(feat)
        if val is None:
            row.append(float(NUMERIC_FILL_DEFAULTS[feat]))
        else:
            row.append(float(val))

    for feat in CATEGORICAL_FEATURES:
        raw = features_dict.get(feat)
        if raw is None:
            row.append(float("nan"))  # XGBoost handles NaN natively; LR imputer fills it
        else:
            normalised = str(raw).strip().lower()
            row.append(IHC_ENCODING.get(normalised, float("nan")))

    return np.array([row], dtype=np.float32)


def missing_mask(features_dict: dict[str, Any]) -> list[str]:
    """
    Return the list of feature names that are None/null in the features_dict.
    Used to populate `missing_fields` in the FeatureSnapshot and trigger
    quality_status warnings.
    """
    return [f for f in ALL_FEATURE_NAMES if features_dict.get(f) is None]


def ood_check(features_dict: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Rule-based Out-of-Distribution (OOD) check against the agreed training range.

    OOD is assessed per explicit rule — NOT by a trained density model.
    This explains model BEHAVIOUR boundaries, not clinical limits.

    Returns
    -------
    is_ood : bool
    reasons : list[str]  Non-empty if is_ood is True.
    """
    reasons: list[str] = []

    ts = features_dict.get("tumour_size_mm")
    if ts is not None and float(ts) > 100.0:
        reasons.append(f"tumour_size_mm={ts} exceeds training range (> 100 mm)")

    pn = features_dict.get("positive_nodes")
    if pn is not None and int(pn) > 30:
        reasons.append(f"positive_nodes={pn} exceeds training range (> 30)")

    g = features_dict.get("grade")
    if g is not None and int(g) not in (1, 2, 3, 4):
        reasons.append(f"grade={g} outside supported range [1–4]")

    ki = features_dict.get("ki67_percent")
    if ki is not None and not (0.0 <= float(ki) <= 100.0):
        reasons.append(f"ki67_percent={ki} outside valid range [0, 100]")

    return bool(reasons), reasons
