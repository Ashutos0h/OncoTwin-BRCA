# Foundation, Data & AI/ML Modules Verification

Verified in the local working tree, preserving contract schemas and existing module boundaries.

| Check | Result |
| --- | --- |
| Five JSON schemas and synthetic examples (`scripts/validate_contracts.py`) | All 5 passed (`clinical-event`, `twin-state`, `feature-snapshot`, `prediction`, `audit-record`) |
| Python test suite (`pytest`) | 222 passed, 1 skipped (SQLite storage; PostgreSQL live integration skipped) |
| Data/FHIR module tests (`pytest data/tests`) | 105 passed (FHIR adapter, compound observations, IHC scoring, ETL, missingness, anti-leakage splitting, validation) |
| AI/ML module tests (`pytest ml/tests`) | 52 passed (preprocessing, OOD heuristics, candidate comparison, Platt calibration, mock & model inference) |
| Frontend test suite (`vitest run`) | 31 passed across 2 test files (`api.test.ts`, `App.test.tsx`) |
| TypeScript verification & Vite production build (`npm run build`) | Passed without error |
| Structural validation smoke check (`python -m data.src.validation`) | `PASS ClinicalEvent (structural validation only)` |

### Scope Status
- **FHIR R4 Adapter**: Implemented. 8 LOINC codes mapped across pathology, biomarker, and diagnosis events. Compound observations with `component[]` supported. ASCO/CAP ordinal and quantitative IHC scoring handled. Bundle conversion with skip log supported.
- **Cohort ETL**: Implemented. Quality validation with impossible-value rejection, missingness calculations, `cohort_to_events()` backend bridge, and patient-level anti-leakage train/test splitting.
- **AI/ML Inference & Training**: Implemented. Feature preprocessor with 8 agreed features, rule-based OOD detector, patient-level anti-leakage training pipeline comparing Logistic Regression and XGBoost, Platt calibration, and dual-mode inference boundary (`predict_demo` for explicit mock, `predict_model` for calibrated real inference).
- **Storage**: Default in-memory and SQLite repository tested. Live PostgreSQL database service and concurrent version-write tests remain a separate backend milestone.
