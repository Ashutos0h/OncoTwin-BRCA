# Frontend Lead

Read root AGENTS.md, README.md, contracts/README.md, all five schemas and
docs/architecture.md. Own `frontend/`; coordinate changes elsewhere.

## First task

The API dashboard already exists. Start by verifying create twin → append event → snapshot → mock prediction → audit in the browser. Add meaningful UI interaction coverage for this flow, failed requests, empty results and missing values; existing tests cover the API client only. Review keyboard access and preserve explicit mock labels. Coordinate any API changes with Backend.

## Acceptance

Run `npm --prefix frontend test`, `npm --prefix frontend run build` and `python scripts/validate_contracts.py` from root.
Deliver a focused PR with behavior, validation results and remaining limitations.
Do not change shared fields to fit module code. Raise contract proposals explicitly.

## Copy into your Codex session

I am the Frontend Lead. Read AGENTS.md and docs/leads/frontend.md and the shared
contracts, then implement the first task inside frontend/. Preserve shared schemas.
Add meaningful tests and report the checks you ran.
