# OncoTwin-BRCA

Research-only breast-cancer digital-twin prototype. This is the shared starter
monorepo for four leads, using synthetic fixtures and a clearly marked mock output.

**Contract status:** the earlier chat's package could not be recovered. The five
schemas here are a new provisional baseline. Read [contracts/README.md](contracts/README.md)
and [pending decisions](docs/contract-decisions.md) before freezing team interfaces.

| Folder | Owner / purpose |
| --- | --- |
| frontend/ | Frontend Lead · React + TypeScript API dashboard |
| backend/ | Backend/Digital Twin Lead · FastAPI events, state, snapshots and audits |
| ml/ | AI/ML Lead · validated deterministic mock inference |
| data/ | Data/FHIR Lead · event validator and adapter/ETL boundaries |
| contracts/ | Shared schemas and linked synthetic examples |
| docs/ | Architecture, ownership, workflow and four lead prompts |
| infra/ | Optional local PostgreSQL |

## 1. Prepare your machine

Install Python 3.11+ (3.12 recommended), Node.js 22.12+ and Git. Docker is optional.
Open a terminal in this repository. Commands below use Windows PowerShell.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts/validate_contracts.py
.\.venv\Scripts\python.exe -m pytest
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
```

If `python` is unavailable but the Windows launcher exists, use `py -3` to create
the venv. On macOS/Linux use `python3` and `.venv/bin/python`. Instructions in module
READMEs use `python` assuming an activated environment; otherwise use the venv path.

## 2. Run the starters

Backend (terminal 1):
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```
Open http://127.0.0.1:8000/health; interactive API docs are at /docs.

Frontend (terminal 2):
```powershell
npm.cmd --prefix frontend run dev
```
Open http://127.0.0.1:5173. The dashboard calls the backend on port 8000.
Create a synthetic twin, append an event, create a snapshot, then generate a mock
prediction and inspect its audit. No database or model download is required.
Default in-memory records disappear when the backend restarts. See module READMEs
for API configuration and optional database persistence.

ML and Data smoke checks:
```powershell
.\.venv\Scripts\python.exe -m ml.src.predict contracts/examples/feature-snapshot.json
.\.venv\Scripts\python.exe -m data.src.validation data/samples/pathology-event.json
```

## 3. Hand off to the team

Follow [publishing and branches](docs/development-workflow.md). Give each member
their [Frontend](docs/leads/frontend.md), [Backend](docs/leads/backend.md),
[AI/ML](docs/leads/ml.md), or [Data/FHIR](docs/leads/data.md) instruction file.
Start in separate clones and work only in the assigned module.

Start with the [team handoff checklist](docs/team-handoff.md), which distinguishes
the current implementation from each lead's next task. The synthetic API workflow
is implemented; FHIR conversion, cohort ETL and trained ML remain unimplemented.
See [architecture](docs/architecture.md) and [optional database setup](infra/README.md).

See [verification results](docs/verification.md) for completed checks and limits.
