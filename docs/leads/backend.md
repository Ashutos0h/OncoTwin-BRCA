# Backend/Digital Twin Lead

Read root AGENTS.md, README.md, contracts/README.md, all five schemas and
docs/architecture.md. Own `backend/`; coordinate changes elsewhere.

## First task

Models, immutable event replay, snapshots, mock inference, linked audits and database repositories already exist. Read backend/README.md and the existing tests first. Add PostgreSQL integration coverage for migrations, persistence across restart and concurrent expected_state_version writes; current database tests use SQLite. Review replay and error policies with the other leads. Own persistence/migrations, audit creation and the ML adapter; preserve the current schema shapes.

## Acceptance

Run `python -m pytest backend/tests` and `python scripts/validate_contracts.py` from root.
Deliver a focused PR with behavior, validation results and remaining limitations.
Do not change shared fields to fit module code. Raise contract proposals explicitly.

## Copy into your Codex session

I am the Backend/Digital Twin Lead. Read AGENTS.md and docs/leads/backend.md and the shared
contracts, then implement the first task inside backend/. Preserve shared schemas.
Add meaningful tests and report the checks you ran.
