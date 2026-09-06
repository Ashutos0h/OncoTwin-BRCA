# Frontend Lead

Read root AGENTS.md, README.md, contracts/README.md, all five schemas and
docs/architecture.md. Own `frontend/`; coordinate changes elsewhere.

## First task

Build the dashboard from contracts/examples with accessible loading, empty, error and missing-data states. Add risk trajectory only once historical predictions exist; label mock results clearly. Agree API consumption with Backend before wiring requests.

## Acceptance

Run `npm --prefix frontend run build` and `python scripts/validate_contracts.py` from root.
Deliver a focused PR with behavior, validation results and remaining limitations.
Do not change shared fields to fit module code. Raise contract proposals explicitly.

## Copy into your Codex session

I am the Frontend Lead. Read AGENTS.md and docs/leads/frontend.md and the shared
contracts, then implement the first task inside frontend/. Preserve shared schemas.
Add meaningful tests and report the checks you ran.
