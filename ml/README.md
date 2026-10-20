# AI/ML Module — OncoTwin-BRCA

This module implements the inference boundary, feature preprocessing, model comparison, Platt calibration, and contract-conforming prediction generation for the breast cancer digital-twin prototype.

## Quick Start & Verification

From repository root:
```powershell
# Run all ML module tests
.\.venv\Scripts\python.exe -m pytest ml/tests -v

# Train and compare models (LogisticRegression vs XGBoost)
.\.venv\Scripts\python.exe -m ml.src.train

# Run mock inference on an example snapshot
.\.venv\Scripts\python.exe -m ml.src.predict contracts/examples/feature-snapshot.json

# Run trained model inference on an example snapshot
.\.venv\Scripts\python.exe -m ml.src.predict contracts/examples/feature-snapshot.json --use-model
```

---

## 1. Feature Preprocessing (`ml.src.preprocess`)

Extracts and encodes the 8 features agreed with the Data/FHIR Lead:

| Feature | Type | Representation / Encoding | Source Event |
|---|---|---|---|
| `tumour_size_mm` | float | Direct float (≥ 0, default 25.0 mm) | `PATHOLOGY_RESULT` |
| `grade` | int | 1–4 (default 2) | `PATHOLOGY_RESULT` |
| `positive_nodes` | int | Integer count (≥ 0, default 0) | `PATHOLOGY_RESULT` |
| `ki67_percent` | float | Percentage `[0.0, 100.0]` (default 20.0%) | `BIOMARKER_RESULT` |
| `her2_status` | float | `negative`: 0.0, `equivocal`: 0.5, `positive`: 1.0, null: NaN | `BIOMARKER_RESULT` |
| `er_status` | float | `negative`: 0.0, `positive`: 1.0, null: NaN | `BIOMARKER_RESULT` |
| `pr_status` | float | `negative`: 0.0, `positive`: 1.0, null: NaN | `BIOMARKER_RESULT` |
| `morphology_code` | string | Tracked in lineage, excluded from model matrix | `DIAGNOSIS` |

### OOD (Out-of-Distribution) Checks
Rule-based bounds detection checking:
- `tumour_size_mm > 100.0`
- `positive_nodes > 30`
- `ki67_percent < 0.0` or `> 100.0`
- `grade not in {1, 2, 3, 4}`

When OOD is detected, `ood_flag=True` and `confidence="low"` are assigned.

---

## 2. Model Training & Comparison (`ml.src.train`)

1. **Synthetic Cohort Generation**:
   Deterministic generation of synthetic patients with realistic correlations between tumor size, grade, nodal involvement, and receptor status.
2. **Anti-Leakage Patient-Level Split**:
   Uses `data.src.etl.patient_level_train_test_split()` to enforce:
   $$\text{train\_patients} \cap \text{val\_patients} \cap \text{test\_patients} = \emptyset$$
3. **Candidate Comparison**:
   - **Logistic Regression**: Pipeline with median imputation, standard scaling, and L2 regularization.
   - **XGBoost**: Tree-based gradient booster with native NaN handling.
   - Evaluated by validation ROC-AUC.
4. **Calibration**:
   Platt scaling (sigmoid calibration) applied to the chosen candidate.
5. **Persistence**:
   Trained model saved to `ml/models/model.pkl`, full evaluation and provenance metadata saved to `ml/models/model_metadata.json`.

---

## 3. Inference Boundary (`ml.src.predict`)

Conforms strictly to `contracts/prediction.schema.json` v0.1.0:
- `predict_demo(snapshot, ..., use_model=False)`: Explicit synthetic mock prediction. Returns `is_mock=True`, `confidence="not_assessed"`, `ood_flag=None`, and mock warning.
- `predict_model(snapshot, ...)`: Real calibrated model inference. Returns `is_mock=False`, versioned model metadata, calibrated probability, and rule-based OOD / confidence assessment.

---

## Ethical & Clinical Boundaries

- **Research prototype only**: This software does not provide clinical diagnosis or treatment recommendations.
- **SHAP Note**: When SHAP explanation values are computed, they explain mathematical model behavior across features — **not clinical causality**.
- **Synthetic Data**: Models trained on synthetic cohorts must never be represented as clinically trained or validated models.
