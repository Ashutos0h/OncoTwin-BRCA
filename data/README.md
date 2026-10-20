# Data/FHIR Module — OncoTwin-BRCA

This module owns FHIR R4 adaptation, synthetic cohort ETL, schema validation, and anti-leakage train/test splitting for the breast cancer digital-twin prototype.

## Quick Start & Verification

From repository root:
```powershell
# Run all data module tests
.\.venv\Scripts\python.exe -m pytest data/tests -v

# Validate JSON schema contracts
.\.venv\Scripts\python.exe scripts/validate_contracts.py

# Structural validation smoke test
.\.venv\Scripts\python.exe -m data.src.validation data/samples/pathology-event.json
```

---

## 1. FHIR R4 Adapter (`data.src.fhir_adapter`)

Translates FHIR R4 `Observation` and `Bundle` resources into schema-conforming `ClinicalEvent` dicts (`contracts/clinical-event.schema.json` v0.1.0).

### Supported LOINC Codes & Mappings

| LOINC Code | Display / Concept | Event Type | Field Name | Supported Values & Conversion |
|---|---|---|---|---|
| `21889-1` | Size Tumor | `PATHOLOGY_RESULT` | `tumour_size_mm` | mm or cm (`cm` multiplied by 10) |
| `33732-9` | Histologic grade | `PATHOLOGY_RESULT` | `grade` | Integer 1–4 (1–3 Nottingham, 4 undifferentiated) |
| `21893-3` | Regional lymph nodes positive | `PATHOLOGY_RESULT` | `positive_nodes` | Integer ≥ 0 |
| `85319-2` | HER2 Ag [Presence] in Tissue.IHC | `BIOMARKER_RESULT` | `her2_status` | Text (`positive`/`negative`/`equivocal`), ordinal scores (`0`, `1+`, `2+`, `3+`), or numeric score 0–3 |
| `85337-4` | ER [Presence] in Tissue.IHC | `BIOMARKER_RESULT` | `er_status` | Text (`positive`/`negative`), abbreviation (`POS`/`NEG`), or % staining (≥ 1% = positive) |
| `85347-3` | PR [Presence] in Tissue.IHC | `BIOMARKER_RESULT` | `pr_status` | Text (`positive`/`negative`), abbreviation (`POS`/`NEG`), or % staining (≥ 1% = positive) |
| `59847-4` | Ki-67 nuclear antigen [%] | `BIOMARKER_RESULT` | `ki67_percent` | Percentage float in range `[0.0, 100.0]` |
| `29308-4` | Diagnosis (morphology) | `DIAGNOSIS` | `morphology_code` | ICD-O-3 code string (e.g. `8500/3`) |

### Compound & Multi-Measurement Observations
Supports observations containing `component[]` arrays (e.g. Receptor Status panels or full pathology panels). All matching components are extracted and merged into a single event payload.

### Bundle Ingestion
`bundle_to_events(bundle, twin_id)` extracts all supported Observation resources, collecting unsupported entries or impossible values into a non-fatal `skip_log`.

---

## 2. Cohort ETL & Anti-Leakage Splitting (`data.src.etl`)

### Cohort Ingestion & Missingness
- `run_etl(source_file)`: Reads synthetic JSON cohorts, validates numeric ranges and categorical values, and flags warnings for unknown fields.
- `compute_missingness(records)`: Calculates per-feature missingness rates across all 8 feature dictionary fields.

### Backend Event Generation
- `cohort_to_events(records)`: Translates cohort records into granular `ClinicalEvent` instances (`PATHOLOGY_RESULT`, `BIOMARKER_RESULT`, `DIAGNOSIS`) ready for ingestion via Backend endpoints (`POST /api/v1/twins/{twin_id}/events`).

### Anti-Leakage Train/Test Split
- `patient_level_train_test_split(records, patient_id_key="twin_id", test_ratio=0.2, seed=42)`:
  - Guarantees zero patient leakage: `set(train_patients) ∩ set(test_patients) == ∅`.
  - Keeps all longitudinal records for a given patient together in either train or test.
  - Preserves intra-patient temporal event ordering.

---

## 3. Synthetic Fixtures (`data/samples/`)

- [`pathology-event.json`](samples/pathology-event.json) — Reference `ClinicalEvent` fixture matching contract example.
- [`fhir-observation-tumour-size.json`](samples/fhir-observation-tumour-size.json) — LOINC `21889-1` observation.
- [`fhir-observation-grade.json`](samples/fhir-observation-grade.json) — LOINC `33732-9` histologic grade observation.
- [`fhir-observation-her2.json`](samples/fhir-observation-her2.json) — Qualitative HER2 observation.
- [`fhir-observation-her2-ordinal.json`](samples/fhir-observation-her2-ordinal.json) — Ordinal score HER2 (`2+`).
- [`fhir-observation-compound-biomarkers.json`](samples/fhir-observation-compound-biomarkers.json) — Compound Observation with `component[]` array for ER, PR, HER2, and Ki-67.
- [`fhir-bundle-synthetic.json`](samples/fhir-bundle-synthetic.json) — Full multi-resource FHIR R4 Bundle.
- [`synthetic-cohort.json`](samples/synthetic-cohort.json) — 3-patient synthetic cohort for ETL and missingness testing.
