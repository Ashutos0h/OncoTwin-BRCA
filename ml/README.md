# AI/ML Lead starter

This module owns the `FeatureSnapshot` -> `Prediction` boundary for OncoTwin-BRCA.

## Current status: Milestone 1 (mock boundary only)

The current implementation is a **mock**. It validates an incoming
`FeatureSnapshot`, returns a schema-valid `Prediction` that preserves the
snapshot lineage, and explicitly flags itself as a mock.

**Not implemented yet (deliberately):**

- Real model training (Logistic Regression, XGBoost)
- Probability calibration (Platt scaling, isotonic regression)
- SHAP feature attribution
- Out-of-distribution detection
- Confidence estimation

These will be added once the feature dictionary, outcome definition, time
horizon, censoring rules and patient-level split protocol are agreed with the
Data and Backend leads.

## Explicit mock indicators

Every output from `predict_demo` must carry:

- `is_mock = True`
- `confidence = "not_assessed"`
- `ood_flag = None`
- `shap_values = []`
- a warning string explaining the mock status

The mock name and version (`oncotwin-brca-mock` / `0.0.0-mock`) are forced by
the module so the output can never be mistaken for a real registered model.

## Running the mock

From the repository root:

```bash
python -m ml.src.predict contracts/examples/feature-snapshot.json