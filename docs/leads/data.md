# Data/FHIR Lead

Read root AGENTS.md, README.md, contracts/README.md, all five schemas and
docs/architecture.md. Own `data/`; coordinate changes elsewhere.

## First task

Define one supported synthetic FHIR R4 Observation mapping with codes, units, provenance and missingness. Reject unsupported or impossible values. Test it against ClinicalEvent. Agree a feature dictionary and cohort endpoint with ML; review database requirements with Backend. Keep raw/processed datasets untracked.

## Acceptance

Run `python -m pytest data/tests` and `python scripts/validate_contracts.py` from root.
Deliver a focused PR with behavior, validation results and remaining limitations.
Do not change shared fields to fit module code. Raise contract proposals explicitly.

## Copy into your Codex session

I am the Data/FHIR Lead. Read AGENTS.md and docs/leads/data.md and the shared
contracts, then implement the first task inside data/. Preserve shared schemas.
Add meaningful tests and report the checks you ran.
