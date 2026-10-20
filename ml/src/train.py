"""
Synthetic training pipeline for OncoTwin-BRCA ML module.

Compares Logistic Regression and XGBoost on a synthetic cohort,
selects the best by validation ROC-AUC, calibrates with Platt scaling,
and saves model + metadata to ml/models/.

Anti-Leakage Policy
--------------------
- Patient-level splits ONLY — uses data.src.etl.patient_level_train_test_split().
- set(train_patients) ∩ set(val_patients) ∩ set(test_patients) == ∅ strictly enforced.
- No feature engineering sees test-set values at any point.

Synthetic Data Disclaimer
--------------------------
- generate_synthetic_cohort() produces random synthetic data only.
- No real clinical datasets, no PHI, no real patient records.
- Trained models from synthetic data MUST NOT be used for any clinical decision.
- All outputs are marked experimental/synthetic in model_metadata.json.

SHAP / Causality
-----------------
- SHAP explains model behaviour, not clinical causality.
- This script does NOT add SHAP; SHAP integration is in predict.py.
- Do not add diagnosis or treatment recommendations.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = Path(__file__).parent.parent / "models"

from ml.src.preprocess import (
    ALL_FEATURE_NAMES,
    FEATURE_SET_VERSION,
    extract_features,
)

# ---------------------------------------------------------------------------
# Outcome Definition
# ---------------------------------------------------------------------------
OUTCOME_LABEL = "recurrence_5yr"   # binary: 1 = distant recurrence within 60 months
HORIZON_MONTHS = 60
TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
# TEST_RATIO = 0.15 (implicit: 1 - TRAIN_RATIO - VAL_RATIO)


# ---------------------------------------------------------------------------
# Synthetic Cohort Generator
# ---------------------------------------------------------------------------

def generate_synthetic_cohort(n_patients: int = 600, seed: int = 42) -> pd.DataFrame:
    """
    Generate a synthetic breast-cancer cohort for model development.

    This data is ENTIRELY SYNTHETIC — no real patient records.
    The outcome is a logistic function of known breast-cancer risk factors;
    it does NOT represent a validated clinical model.

    Parameters
    ----------
    n_patients : int
        Number of unique synthetic patients to generate.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    pd.DataFrame
        One row per patient with feature columns and outcome label.
    """
    rng = np.random.default_rng(seed)

    tumour_size_mm = rng.uniform(5.0, 80.0, n_patients)
    grade = rng.choice([1, 2, 3, 4], size=n_patients, p=[0.15, 0.35, 0.40, 0.10])
    positive_nodes = rng.poisson(lam=2.5, size=n_patients).clip(0, 30)
    ki67_percent = rng.uniform(1.0, 80.0, n_patients)

    # IHC status — marginal distributions approximate real BRCA epidemiology (synthetic)
    her2 = rng.choice(["negative", "equivocal", "positive"], size=n_patients, p=[0.70, 0.10, 0.20])
    er = rng.choice(["positive", "negative"], size=n_patients, p=[0.75, 0.25])
    pr = rng.choice(["positive", "negative"], size=n_patients, p=[0.65, 0.35])

    # Missing data (~15% missingness for biomarkers, reflecting clinical reality)
    ki67_percent = np.where(rng.random(n_patients) < 0.15, np.nan, ki67_percent)
    her2 = np.where(rng.random(n_patients) < 0.10, None, her2)
    er = np.where(rng.random(n_patients) < 0.05, None, er)
    pr = np.where(rng.random(n_patients) < 0.08, None, pr)

    # Synthetic outcome: logistic function of risk factors (NOT a real survival model)
    log_odds = (
        -2.0
        + 0.03 * tumour_size_mm
        + 0.5 * (grade - 1)
        + 0.15 * positive_nodes
        + 0.02 * np.where(np.isnan(ki67_percent), 20.0, ki67_percent)
        + 0.4 * np.where(her2 == "positive", 1.0, 0.0)
        - 0.8 * np.where(er == "positive", 1.0, 0.0)
    )
    prob_recurrence = 1.0 / (1.0 + np.exp(-log_odds))
    outcome = (rng.random(n_patients) < prob_recurrence).astype(int)

    twin_ids = [f"SYNTHETIC_TWIN_{i+1:04d}" for i in range(n_patients)]

    df = pd.DataFrame({
        "twin_id": twin_ids,
        "tumour_size_mm": tumour_size_mm,
        "grade": grade,
        "positive_nodes": positive_nodes,
        "ki67_percent": ki67_percent,
        "her2_status": her2,
        "er_status": er,
        "pr_status": pr,
        OUTCOME_LABEL: outcome,
    })
    return df


def _encode_features(df: pd.DataFrame) -> np.ndarray:
    """
    Encode a cohort DataFrame into a feature matrix using the same
    logic as extract_features() in preprocess.py.
    """
    rows = []
    for _, rec in df.iterrows():
        row = extract_features(rec.to_dict())
        rows.append(row[0])
    return np.array(rows, dtype=np.float32)


# ---------------------------------------------------------------------------
# Model Building
# ---------------------------------------------------------------------------

def _build_lr_pipeline() -> Pipeline:
    """Logistic Regression with median imputation and standard scaling."""
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("classifier", LogisticRegression(max_iter=500, random_state=42, C=1.0)),
    ])


def _build_xgb_pipeline() -> XGBClassifier:
    """XGBoost with native NaN handling."""
    return XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
        verbosity=0,
    )


# ---------------------------------------------------------------------------
# Main Training Entry Point
# ---------------------------------------------------------------------------

def train(n_patients: int = 600, seed: int = 42, save: bool = True) -> dict:
    """
    Full training pipeline:
      1. Generate synthetic cohort.
      2. Patient-level train / val / test split.
      3. Encode features.
      4. Train LR and XGBoost.
      5. Select by validation ROC-AUC.
      6. Calibrate (Platt scaling).
      7. Evaluate on held-out test set.
      8. Save model + metadata.

    Parameters
    ----------
    n_patients : int
    seed : int
    save : bool  Whether to persist model + metadata to disk.

    Returns
    -------
    dict  Metadata / results dict (also written to model_metadata.json if save=True).
    """
    print("Generating synthetic cohort …")
    df = generate_synthetic_cohort(n_patients=n_patients, seed=seed)

    # ---- Patient-level split (anti-leakage) --------------------------------
    records = df.to_dict(orient="records")

    # Import the anti-leakage splitter from the data module
    sys.path.insert(0, str(ROOT))
    from data.src.etl import patient_level_train_test_split

    # 70 / 30 split → then 50/50 the 30% for val and test (→ 70/15/15)
    train_recs, rest_recs = patient_level_train_test_split(
        records, patient_id_key="twin_id", test_ratio=0.30, seed=seed
    )
    val_recs, test_recs = patient_level_train_test_split(
        rest_recs, patient_id_key="twin_id", test_ratio=0.50, seed=seed
    )

    # Verify zero leakage across all three splits
    train_ids = {r["twin_id"] for r in train_recs}
    val_ids = {r["twin_id"] for r in val_recs}
    test_ids = {r["twin_id"] for r in test_recs}
    assert not (train_ids & val_ids), "Train/val patient leakage detected!"
    assert not (train_ids & test_ids), "Train/test patient leakage detected!"
    assert not (val_ids & test_ids), "Val/test patient leakage detected!"
    print(f"  Train={len(train_recs)}  Val={len(val_recs)}  Test={len(test_recs)}")

    def _to_df(recs):
        return pd.DataFrame(recs)

    df_train = _to_df(train_recs)
    df_val = _to_df(val_recs)
    df_test = _to_df(test_recs)

    X_train = _encode_features(df_train)
    y_train = df_train[OUTCOME_LABEL].values
    X_val = _encode_features(df_val)
    y_val = df_val[OUTCOME_LABEL].values
    X_test = _encode_features(df_test)
    y_test = df_test[OUTCOME_LABEL].values

    # ---- Train candidates --------------------------------------------------
    print("Training Logistic Regression …")
    lr = _build_lr_pipeline()
    lr.fit(X_train, y_train)
    lr_val_auc = roc_auc_score(y_val, lr.predict_proba(X_val)[:, 1])
    print(f"  LR  val ROC-AUC: {lr_val_auc:.4f}")

    print("Training XGBoost …")
    xgb = _build_xgb_pipeline()
    xgb.fit(X_train, y_train)
    xgb_val_auc = roc_auc_score(y_val, xgb.predict_proba(X_val)[:, 1])
    print(f"  XGB val ROC-AUC: {xgb_val_auc:.4f}")

    # ---- Select and calibrate ----------------------------------------------
    if lr_val_auc >= xgb_val_auc:
        selected_name = "LogisticRegression"
        raw_model = lr
    else:
        selected_name = "XGBClassifier"
        raw_model = xgb

    print(f"Selected: {selected_name}. Calibrating (Platt scaling) …")
    # cv=2 does internal cross-val calibration on val set without needing prefit flag
    calibrated = CalibratedClassifierCV(raw_model, method="sigmoid", cv=2)
    calibrated.fit(X_val, y_val)

    # ---- Evaluate on test set ----------------------------------------------
    test_probs = calibrated.predict_proba(X_test)[:, 1]
    test_auc = roc_auc_score(y_test, test_probs)
    test_brier = brier_score_loss(y_test, test_probs)
    print(f"  Test ROC-AUC : {test_auc:.4f}")
    print(f"  Test Brier   : {test_brier:.4f}")

    # ---- Build metadata ----------------------------------------------------
    model_version = f"synthetic-0.2.0-{seed}"
    metadata = {
        "model_name": selected_name,
        "model_version": model_version,
        "feature_set_version": FEATURE_SET_VERSION,
        "feature_names": ALL_FEATURE_NAMES,
        "outcome_label": OUTCOME_LABEL,
        "horizon_months": HORIZON_MONTHS,
        "is_synthetic": True,
        "clinical_use": "PROHIBITED — synthetic research prototype only",
        "n_train": len(train_recs),
        "n_val": len(val_recs),
        "n_test": len(test_recs),
        "candidates": {
            "LogisticRegression": {"val_roc_auc": round(lr_val_auc, 4)},
            "XGBClassifier": {"val_roc_auc": round(xgb_val_auc, 4)},
        },
        "selected": selected_name,
        "calibration": "Platt (sigmoid), fitted on val set",
        "test_roc_auc": round(test_auc, 4),
        "test_brier_score": round(test_brier, 4),
        "ood_rules": {
            "tumour_size_mm_max": 100.0,
            "positive_nodes_max": 30,
            "ki67_percent_range": [0.0, 100.0],
            "grade_range": [1, 4],
        },
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "shap_note": "SHAP explains model behaviour only — not clinical causality. "
                     "No diagnosis or treatment recommendations should be derived.",
    }

    if save:
        MODELS_DIR.mkdir(exist_ok=True)
        model_path = MODELS_DIR / "model.pkl"
        meta_path = MODELS_DIR / "model_metadata.json"
        joblib.dump(calibrated, model_path)
        meta_path.write_text(json.dumps(metadata, indent=2))
        print(f"Saved model -> {model_path}")
        print(f"Saved metadata -> {meta_path}")

    return metadata


if __name__ == "__main__":
    meta = train()
    print(json.dumps(meta, indent=2))
