# ML Specification — OncoTwin-BRCA

## Feature Dictionary (agreed with Data/FHIR Lead)

All features sourced from the agreed `FEATURE_DICT` in `data/src/fhir_adapter.py`.

| Feature | Type | Constraints | Source Event |
|---|---|---|---|
| `tumour_size_mm` | float | ≥ 0 | `PATHOLOGY_RESULT` |
| `grade` | int | 1–4 | `PATHOLOGY_RESULT` |
| `positive_nodes` | int | ≥ 0 | `PATHOLOGY_RESULT` |
| `her2_status` | str\|null | positive/negative/equivocal | `BIOMARKER_RESULT` |
| `er_status` | str\|null | positive/negative | `BIOMARKER_RESULT` |
| `pr_status` | str\|null | positive/negative | `BIOMARKER_RESULT` |
| `ki67_percent` | float\|null | 0–100 | `BIOMARKER_RESULT` |
| `morphology_code` | str\|null | ICD-O-3 string | `DIAGNOSIS` |

## Outcome, Horizon & Censoring

- **Outcome**: Binary 5-year distant recurrence risk (1 = recurrence within 5 years, 0 = recurrence-free).
- **Horizon**: 60 months from diagnosis date.
- **Censoring Policy**: Patients lost to follow-up before 60 months without a recurrence event are right-censored. In this synthetic prototype they are excluded from binary classification. Survival analysis (e.g. Cox PH, Kaplan–Meier) is the appropriate method for right-censored data — flagged as a future milestone.
- **Clinical note**: This is a synthetic research prototype. No clinical decisions may be made from its outputs.

## Patient-Level Splits

- **Patient-level**: 70% Train / 15% Validation / 15% Test.
- Implemented via `data.src.etl.patient_level_train_test_split()` — zero patient leakage guaranteed.
- Stratified by outcome where possible.

## Model Comparison

- **Logistic Regression** with median imputation and feature scaling (Pipeline).
- **XGBoost** with native missing-value handling.
- Selection criterion: validation-set ROC-AUC.
- **Calibration**: Platt scaling (sigmoid calibration) applied to selected model.
- **Evaluation metrics**: ROC-AUC, Brier Score, calibration slope (reported in metadata).

## OOD (Out-of-Distribution) Heuristics

Explicit rule-based boundary check (not a trained model):
- `tumour_size_mm` > 100 mm
- `positive_nodes` > 30
- `grade` not in {1, 2, 3, 4}
- `ki67_percent` > 100 or < 0

OOD triggers `ood_flag=True` and `confidence="low"` in prediction output.

## SHAP Constraint

SHAP values explain model *behaviour* relative to feature inputs — **not clinical causality**.
SHAP is only generated when a real trained model is loaded (`is_mock=False`).
No SHAP, OOD confidence, or clinical interpretation is fabricated for mock outputs.

## Mock Boundary

All prediction outputs carry `is_mock=true` until:
1. A real trained model file is present at `ml/models/model.pkl`.
2. The file was produced by `ml/src/train.py` with versioned metadata at `ml/models/model_metadata.json`.

Mock outputs always carry a synthetic warning string. Real outputs must never be presented as trained results without this metadata present.
