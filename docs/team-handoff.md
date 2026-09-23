# Team handoff checklist

Use the existing repository at `C:\Users\vashu\Desktop\OncoTwin-BRCA - Copy`.
The conversation workspace is not a second application repository.

## Owner: prepare the shared baseline

1. Read README.md and run its setup/check commands. All seven planned folders,
   root AGENTS.md, .gitignore, .env.example, five schemas and five fixtures exist.
2. Keep the existing contracts authoritative. Their original attachment was not
   recovered; adoption/reconciliation remains recorded in contract-decisions.md.
   No schema or fixture was changed during this handoff update.
3. Review the current uncommitted frontend/backend implementation and shared docs.
   A clone only receives committed and pushed files, not this working directory.
4. Follow development-workflow.md to publish the reviewed baseline to the existing
   remote. Publication and remote access were not verified in this session.
5. Give each lead a separate clone and their instruction file below. Each lead
   runs the setup once and works on a separate module branch.

## Independent next tasks

| Lead | Current starting point | Next deliverable | Instructions |
| --- | --- | --- | --- |
| Frontend | API dashboard and four API client tests | Browser workflow/error/missing-data interaction tests and accessibility review | [Frontend](leads/frontend.md) |
| Backend/Digital Twin | Event replay, snapshots, mock inference, audits, migrations | PostgreSQL migration/restart/concurrency integration tests; policy review | [Backend](leads/backend.md) |
| AI/ML | Contract-validated constant mock | Tested inference boundary and proposed feature/outcome/split specification before training | [AI/ML](leads/ml.md) |
| Data/FHIR | Event validator; adapter and ETL stubs | One supported synthetic Observation mapping with provenance and rejection tests | [Data/FHIR](leads/data.md) |

The ML and Data leads can develop with the shared fixtures independently of the
running API. Frontend can use the in-memory backend without installing PostgreSQL.
Backend owns the adapter to ML; changes at that boundary require both leads' review.

## Integration acceptance

Start both services using README.md. Create a synthetic twin, append an event,
inspect state, create a snapshot, generate a mock prediction, and inspect its audit.
Check that twin, state, snapshot, prediction, audit, model and data versions retain
consistent linkage. Keep null/missing values visible and mock outputs explicit.
The automated backend suite covers the synthetic pipeline; manual browser acceptance
and live PostgreSQL verification still need to be completed.

Affected leads review shared interface changes before merging. Each PR states its
behavior, checks, contract impact and limitations. See verification.md for this
working tree's local check results.
