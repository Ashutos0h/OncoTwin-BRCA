# Backend/Digital Twin Lead

Read root AGENTS.md, README.md, contracts/README.md, all five schemas and
docs/architecture.md. Own `backend/`; coordinate changes elsewhere.

## First task

Implement models matching the five schemas and an in-memory immutable event store. Propose and document POST /api/v1/twins, POST /api/v1/twins/{id}/events and GET /api/v1/twins/{id}/state. Test duplicate IDs, out-of-order events, deterministic replay and lineage. Own persistence/migrations, audit creation and ML integration.

## Acceptance

Run `python -m pytest backend/tests` and `python scripts/validate_contracts.py` from root.
Deliver a focused PR with behavior, validation results and remaining limitations.
Do not change shared fields to fit module code. Raise contract proposals explicitly.

## Copy into your Codex session

I am the Backend/Digital Twin Lead. Read AGENTS.md and docs/leads/backend.md and the shared
contracts, then implement the first task inside backend/. Preserve shared schemas.
Add meaningful tests and report the checks you ran.
