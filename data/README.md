# Data Engineering, FHIR & Database Foundation — OncoTwin-BRCA

This module owns dataset acquisition, FHIR R4 adaptation, end-to-end ETL processing, canonical data schemas, PostgreSQL persistence, and anti-leakage train/validation/test splitting for the breast cancer digital-twin prototype.

---

## Quick Start & Verification

From repository root:
```powershell
# 1. Run all data module tests (126 tests)
.\.venv\Scripts\python.exe -m pytest data/tests -v

# 2. Execute full reproducible ETL and ingestion pipeline (METABRIC + Synthea + TCGA)
.\.venv\Scripts\python.exe -m data.src.pipeline --dataset all

# 3. Validate JSON schema contracts
.\.venv\Scripts\python.exe scripts/validate_contracts.py

# 4. Structural validation smoke test
.\.venv\Scripts\python.exe -m data.src.validation data/samples/pathology-event.json
```

---

## 1. Dataset Acquisition (`data.src.acquisition`)

| Dataset | Role in Study | Status & Implementation |
|---|---|---|
| **METABRIC** | Primary model development ($N=2{,}509$) | Automated retrieval from cBioPortal API, deduplication, competing risk handling, 5-year recurrence labeling. |
| **TCGA-BRCA** | External validation feasibility | Automated feasibility assessment: median DFS is 25.0 months, 71.9% censored before 5 years, discrete T stages only. Formally established as statistically infeasible. |
| **Synthea** | Synthetic FHIR R4 simulation | Cohort generator for complete clinical trajectories: `Patient`, `Encounter`, `DiagnosticReport`, and `Observation`. |
| **TCIA** | Multimodal imaging stretch goal | Defined contract and specification for DICOM breast MR/MG segmentation and radiomics. Preserved strictly as optional stretch goal. |

---

## 2. Canonical Data Schema & Entities (`data.src.canonical`)

Defines typed Pydantic and SQLAlchemy representations for the 10 core entities:

1. **`Twin`**: Digital-twin lifecycle anchor entity (`twin_id`, `created_at`, `state_version`, `status`).
2. **`PatientProfile`**: Demographic metadata (`patient_id`, `twin_id`, `mrn`, `gender`, `birth_date`).
3. **`ClinicalEvent`**: Immutable event conforming to `contracts/clinical-event.schema.json` v0.1.0 (`event_id`, `twin_id`, `event_type`, `effective_time`, `received_time`, `source`, `quality_status`, `provenance`, `payload`, `schema_version`).
4. **`Observation`**: Discrete measurement with LOINC code, numeric/string values, unit, and status.
5. **`TumourProfile`**: Harmonized 8-feature representation with per-feature missingness tracking.
6. **`FeatureSnapshot`**: Immutable state snapshot with lineage to `state_version` and input `event_ids`.
7. **`Prediction`**: Prognostic risk estimate with probability, TreeSHAP values, and OOD flag.
8. **`ModelVersion`**: Registered AI/ML algorithm metadata, hyperparameters, and evaluation metrics.
9. **`DataVersion`**: Provenance record fingerprinting raw and cleaned datasets with SHA-256 hashes.
10. **`AuditLog`**: Tamper-evident ledger linking every prediction to its snapshot, state version, and actor.

---

## 3. End-to-End ETL Pipeline (`data.src.etl` & `data.src.pipeline`)

```
Raw Dataset
    ↓
Schema Validation
    ↓
Cleaning & Deduplication
    ↓
Normalization
    ↓
Missingness Detection & Masking
    ↓
Anti-Leakage Splitting (Zero Patient Overlap)
    ↓
Canonical Mapping (ClinicalEvent, PatientProfile, TumourProfile)
    ↓
Database Ingestion (PostgreSQL / SQLite Event Store)
```

### Key Responsibilities Implemented:
- **Duplicate Removal**: Patient- and event-level deduplication preserving primary primary tumour specimens.
- **Unit Normalization**: Tumour size normalized from cm to mm; percentage values validated $[0, 100]$; ordinal HER2 scores mapped ($0, 1+ \to \text{neg}$, $2+ \to \text{equiv}$, $3+ \to \text{pos}$).
- **Invalid Value Detection**: Rejects negative dimensions, node counts $< 0$, or Nottingham grades outside $1\text{--}4$.
- **Timestamp Normalization**: Coerces heterogeneous dates to strict ISO 8601 UTC format (`YYYY-MM-DDTHH:MM:SSZ`).
- **Missing-Value Masks**: Computes per-feature missingness rates and generates binary 0/1 masks for every record.
- **Data Provenance & Versioning**: SHA-256 dataset fingerprinting and automated `DataVersion` registration.

---

## 4. FHIR R4 Adapter (`data.src.fhir_adapter`)

Translates FHIR R4 resources into schema-conforming canonical events (`contracts/clinical-event.schema.json` v0.1.0):

### Supported LOINC Codes
- `21889-1`: Size Tumor (stored as mm)
- `33732-9`: Histologic grade (Nottingham 1–3 + Grade 4)
- `21893-3`: Regional lymph nodes positive count
- `85319-2`: HER2 Ag IHC (qualitative, ordinal $0\text{--}3+$, or numeric score)
- `85337-4`: ER IHC (qualitative, abbreviation, or $\%$ staining)
- `85347-3`: PR IHC (qualitative, abbreviation, or $\%$ staining)
- `59847-4`: Ki-67 nuclear antigen labeling index ($\%$)
- `29308-4`: Histologic morphology (ICD-O-3 code)

### Supported FHIR R4 Resource Types
- `Observation`: Single and compound observations via `component[]` arrays.
- `DiagnosticReport`: Extracts contained observations, conclusion text, and morphology codes.
- `Patient`: Demographics (gender, birth date, MRN) mapped to `PatientProfile`.
- `Encounter`: Mapped to `FOLLOW_UP` or `TREATMENT` canonical clinical events.
- `Bundle`: Synthea and clinical collection bundles parsed with automated error skipping into `skip_log`.

---

## 5. PostgreSQL Schema & Migrations (`backend.app.database`)

- **JSONB Strategy**: Native PostgreSQL `JSONB` for event documents, snapshot feature dictionaries, and audit logs with GIN index compatibility.
- **Foreign Keys**: Cascading and relational integrity between `twins`, `clinical_events`, `patient_profiles`, `tumour_profiles`, `feature_snapshots`, `predictions`, and `audit_records`.
- **Alembic Migrations**:
  - `0001_initial_persistence`: Base tables and indexes.
  - `0002_twin_state_version`: Atomic optimistic locking and state version counter.
  - `0003_canonical_entities`: Added `patient_profiles`, `observations`, `tumour_profiles`, `model_versions`, and `data_versions`.
- **Audit & Lineage Queries**:
  - `get_audit_trail_for_twin(twin_id)`
  - `get_prediction_lineage(prediction_id)`: Unpacks prediction $\to$ snapshot $\to$ twin state $\to$ referenced clinical events.

---

## 6. Dataset Splitting & Leakage Prevention

- **Anti-Leakage Invariant**:
  $$\text{Train Patients} \cap \text{Validation Patients} = \emptyset$$
  $$\text{Train Patients} \cap \text{Test Patients} = \emptyset$$
  $$\text{Validation Patients} \cap \text{Test Patients} = \emptyset$$
- Longitudinal records for any individual patient are strictly constrained to a single partition.
- Reproducible random seeds (`SEED = 42`) guarantee deterministic re-execution.
