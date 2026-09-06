# OncoTwin-BRCA engineering rules

Research-only prototype. Read README.md, contracts/README.md, all five schemas,
docs/architecture.md, and your lead instruction file in docs/leads/ before editing.

- frontend/: Frontend Lead; backend/: Backend/Digital Twin Lead;
  ml/: AI/ML Lead; data/: Data/FHIR Lead.
- Work inside your module unless the user explicitly authorizes shared work.
- contracts/, infra/, root tooling and shared docs require coordinated review.
- Schemas are authoritative for implementation. Their provisional origin is
  documented; do not represent them as the recovered original package.
- Do not rename fields or change schemas silently. Explain required changes and
  obtain team/user authorization, then record versioning and migration decisions.
- Keep clinical events immutable. Preserve provenance, missingness and versions.
- Every prediction must link model/data/state versions, snapshot ID and audit ID.
- Never fabricate missing clinical inputs or present mock outputs as trained results.
- SHAP explains model behavior, not clinical causality. Do not add diagnosis or
  treatment recommendations. Do not commit patient records, datasets or credentials.
- Prevent patient-level and temporal train/test leakage.
- Add meaningful tests for behavior and cross-module boundaries; run relevant tests
  and contract checks before committing. Report checks that could not run.
