# Backend and Digital Twin API

The backend validates all five shared contract shapes with Pydantic and supports
twin creation, immutable event acceptance, deterministic state reconstruction,
feature snapshots, mock predictions, and linked audits. It can run in temporary
in-memory mode or durable PostgreSQL mode. It remains a research-only service.

Run from repository root after activating the Python environment:

```powershell
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` for the generated API documentation.

Local development defaults to authentication disabled so Swagger remains easy to
use. Records are temporary unless `DATABASE_URL` is configured.

With no `DATABASE_URL`, the application uses in-memory storage. To use PostgreSQL,
start the database defined in `infra/docker-compose.yml`, set `DATABASE_URL`, run the
migration, and start the same Uvicorn command:

```powershell
$env:DATABASE_URL="postgresql+psycopg://oncotwin:YOUR_PASSWORD@127.0.0.1:5432/oncotwin"
python -m alembic -c backend/alembic.ini upgrade head
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Use the password placed in the root `.env` file for Docker. The application does not
create tables automatically; migrations are required. `/health` reports `database`
when database repositories are configured, but it is currently a process check and
does not query PostgreSQL.

## API

| Method | Path | Success | Purpose |
| --- | --- | --- | --- |
| GET | `/health` | 200 | Process health only |
| GET | `/ready` | 200 | Verify configured storage is reachable and migrated |
| GET | `/api/v1/twins` | 200 | List twins and current state versions |
| POST | `/api/v1/twins` | 201 | Create an empty twin from `{"twin_id":"..."}` |
| POST | `/api/v1/twins/{twin_id}/events` | 201 | Validate and append a ClinicalEvent |
| GET | `/api/v1/twins/{twin_id}/events` | 200 | List events in replay order |
| GET | `/api/v1/twins/{twin_id}/state` | 200 | Replay events into TwinState |
| POST | `/api/v1/twins/{twin_id}/snapshots` | 201 | Create and retain a FeatureSnapshot |
| GET | `/api/v1/twins/{twin_id}/snapshots` | 200 | List newest snapshots first |
| POST | `/api/v1/twins/{twin_id}/snapshots/{snapshot_id}/predictions` | 201 | Run mock inference and save prediction/audit |
| GET | `/api/v1/predictions/{prediction_id}` | 200 | Retrieve one prediction |
| GET | `/api/v1/twins/{twin_id}/predictions` | 200 | List newest predictions first |
| GET | `/api/v1/audits/{audit_id}` | 200 | Retrieve a prediction audit record |
| GET | `/api/v1/twins/{twin_id}/audits` | 200 | List newest audit records first |

History endpoints return `items`, `total`, `limit`, and `offset`. The default limit
is 50, the maximum is 200, and offset starts at zero. For example:

```text
GET /api/v1/twins/SYNTHETIC_TWIN_001/events?limit=20&offset=0
```

The local frontend origins `http://127.0.0.1:5173` and `http://localhost:5173` are
allowed by default. Override them with a comma-separated `CORS_ORIGINS` environment
variable.

## Configuration and access

| Variable | Development default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | `development`, `test`, or `production` |
| `DATABASE_URL` | unset | SQLAlchemy PostgreSQL or SQLite URL |
| `CORS_ORIGINS` | local Vite origins | Comma-separated browser origins |
| `AUTH_ENABLED` | `false` | Require API keys for `/api/v1` routes |
| `READER_API_KEY` | unset | Read-only API key |
| `WRITER_API_KEY` | unset | Read and write API key |
| `LOG_LEVEL` | `INFO` | Python logging level |

Set `AUTH_ENABLED=true` to protect the API, then send a key in the `X-API-Key`
header. The writer key can call every endpoint. The reader key can call GET
endpoints and receives 403 from write endpoints. `/health`, `/ready`, `/docs`, and
the OpenAPI document stay public for orchestration and discovery.

Production mode fails fast unless PostgreSQL storage and authentication are both
configured. Reader and writer keys must differ, must each contain at least 32
characters, and wildcard CORS is rejected.
Every response includes `X-Request-ID` and `X-Process-Time-Ms`. Access logs contain
method, route template, status, duration, and request ID; identifiers, bodies, and
API keys are not logged.

Event creation accepts an optional `expected_state_version` query parameter. Send
zero for the first event and the last state version for later events. A stale value
returns 412 without writing the event:

```text
POST /api/v1/twins/SYNTHETIC_TWIN_001/events?expected_state_version=1
```

The state endpoint returns the current version as an `ETag` response header. Version
checks are performed inside the in-memory lock or a PostgreSQL row lock. Omitting the
parameter remains supported for simple clients, but coordinated integrations should
send it to prevent lost updates.

Duplicate twin or event IDs return 409. Unknown twins return 404. Path/body twin ID
mismatches, malformed events, and events marked `quality_status: invalid` return 422.
An empty twin returns 409 from the state endpoint because the TwinState contract
requires a positive state version and at least one value.

## Replay policy

Events are immutable canonical JSON records in memory. Event IDs are unique across
all twins. Out-of-order events are accepted, then sorted by `effective_time`,
`received_time`, and `event_id`. Each event payload updates only the keys it contains;
an explicit null marks that key missing. The final ordered event supplies `as_of` and
`data_version`. State version is the number of accepted events. Warning-quality event
IDs are included in `quality_warnings`.

Snapshot creation first reconstructs the latest state, then copies its lineage,
values, and missing fields into a new immutable FeatureSnapshot. Every request creates
a new UUID-based snapshot ID. The current feature-set version is `demo-0.1.0`.

Prediction persistence calls an `InferenceEngine` interface. The default
`MockInferenceEngine` adapts the existing synthetic ML placeholder. Its result is
validated against the authoritative Prediction contract before the prediction and
audit are saved.

These are backend policies because the provisional contracts do not define replay.
They require review before PostgreSQL migration or cross-module integration.

## Current limitations

- Restarting loses records only in the default in-memory mode. PostgreSQL mode keeps
  twins, events, snapshots, predictions, audits, and snapshot-to-event lineage.
- Correction events, mandatory concurrency preconditions, database backups, key
  rotation, and production database operations require a deployment policy.
- Prediction uses the existing constant mock ML function. It is not trained,
  calibrated, clinically meaningful, or suitable for patient decisions.
- Payload keys have structural validation only; clinical units and domain rules must
  be agreed with the Data/FHIR and ML leads.
- The AuditRecord schema requires prediction fields even for other action types;
  this implementation creates audit records only for `PREDICTION_CREATED`.

Run `python -m pytest backend/tests` and `python scripts/validate_contracts.py` before
committing backend changes.
