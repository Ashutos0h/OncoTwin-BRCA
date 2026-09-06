# Architecture and first milestone

Data/FHIR → ClinicalEvent → Backend event store/replay → TwinState →
FeatureSnapshot → ML → Prediction → Backend AuditRecord → Frontend.

Current runnable scope: five linked synthetic fixtures; schema validator; health
API; constant mock prediction; structural event validation; React fixture view.
These components run independently. An end-to-end API pipeline is NOT implemented.

Backend owns state reconstruction and application persistence. Data owns adapters,
ETL and source semantics. ML owns model preprocessing and inference; Backend and ML
agree snapshot feature meanings. Frontend consumes contract data, not ML internals.

First integration milestone: accept one validated synthetic event, replay state,
create snapshot, call mock inference with reserved audit/prediction IDs, persist
prediction plus audit atomically, and show the result. Test lineage across the flow.
Agree event ordering, duplicates, API request/error envelopes and feature dictionary
before integration. The schemas do not define these policies automatically.

Later: PostgreSQL migrations, richer synthetic FHIR, reviewed cohort ETL, patient
and time-aware evaluation, trained/calibrated models, explanations and dashboard.
No real datasets, clinical decisions or treatment recommendations belong in this base.
