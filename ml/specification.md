# ML Specification

## Feature Dictionary
- `tumour_size_mm` (float): Tumor size in millimeters. Source: PATHOLOGY_RESULT.
- `grade` (int): Tumor grade (1-3). Source: PATHOLOGY_RESULT.
- `positive_nodes` (int): Number of positive lymph nodes. Source: PATHOLOGY_RESULT.

## Outcome, Horizon, Censoring
- **Outcome**: 5-year overall survival (binary: 1 = survival, 0 = mortality).
- **Horizon**: 5 years from the first `DIAGNOSIS` event.
- **Censoring**: Patients lost to follow-up before 5 years without experiencing the outcome are right-censored and excluded from simple binary classification; to be handled by survival analysis in future iterations.

## Splits
- **Patient-level split**: 70% Train, 15% Validation, 15% Test.
- Stratified by outcome and age.
- Strict patient separation: no single patient's events leak across splits.
