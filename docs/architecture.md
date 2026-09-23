# Architecture and first milestone

Data/FHIR → ClinicalEvent → Backend event store/replay → TwinState →
FeatureSnapshot → ML → Prediction → Backend AuditRecord → Frontend.

Current runnable scope: five linked synthetic fixtures; schema validator; FastAPI
twin/event/state/snapshot/prediction/audit endpoints; constant mock inference;
structural event validation; and a React dashboard consuming the API. Storage
defaults to memory, with optional database repositories and Alembic migrations.
The synthetic API pipeline is implemented and covered by backend tests. FHIR
mapping, cohort ETL and model training remain explicit unimplemented boundaries.

Backend owns state reconstruction and application persistence. Data owns adapters,
ETL and source semantics. ML owns model preprocessing and inference; Backend and ML
agree snapshot feature meanings. Frontend consumes contract data, not ML internals.

Implemented synthetic milestone: accept one validated synthetic event, replay state,
create snapshot, call mock inference with reserved audit/prediction IDs, persist
prediction plus audit atomically, and show the result. Test lineage across the flow.
Backend policies for ordering, duplicates and API envelopes are documented in
backend/README.md. Leads must review these and agree a feature dictionary before
extending integration. The schemas do not define these policies automatically.

Next: verify migrations and concurrency against PostgreSQL, richer synthetic FHIR, reviewed cohort ETL, patient
and time-aware evaluation, trained/calibrated models, explanations and dashboard.
No real datasets, clinical decisions or treatment recommendations belong in this base.
