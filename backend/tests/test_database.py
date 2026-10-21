import json
import os
import pytest
from pathlib import Path
import threading

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from backend.app.database import Base, build_engine, create_database_stores
from backend.app.main import create_app
from scripts.validate_contracts import validate

ROOT = Path(__file__).resolve().parents[2]

def sqlite_url(path: Path) -> str:
    return f"sqlite+pysqlite:///{path.as_posix()}"

def database_app(database_url: str):
    stores = create_database_stores(database_url)
    return create_app(*stores, storage_mode="database")

def test_initial_migration_creates_all_tables(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database_url = sqlite_url(tmp_path / "migration.db")
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    tables = set(inspect(build_engine(database_url)).get_table_names())
    assert tables == {
        "alembic_version",
        "audit_records",
        "clinical_events",
        "data_versions",
        "feature_snapshots",
        "model_versions",
        "observations",
        "patient_profiles",
        "predictions",
        "tumour_profiles",
        "twins",
    }

    command.downgrade(config, "base")
    remaining = set(inspect(build_engine(database_url)).get_table_names())
    assert remaining == {"alembic_version"}

def test_full_api_flow_survives_application_restart(tmp_path):
    database_url = sqlite_url(tmp_path / "persistent.db")
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    event = json.loads((ROOT / "contracts/examples/clinical-event.json").read_text())
    twin_id = event["twin_id"]

    with TestClient(database_app(database_url)) as first:
        assert first.get("/health").json()["mode"] == "database"
        assert first.post("/api/v1/twins", json={"twin_id": twin_id}).status_code == 201
        accepted = first.post(f"/api/v1/twins/{twin_id}/events", json=event)
        assert accepted.status_code == 201
        assert accepted.json()["state_version"] == 1
        snapshot = first.post(f"/api/v1/twins/{twin_id}/snapshots").json()
        prediction = first.post(
            f'/api/v1/twins/{twin_id}/snapshots/{snapshot["snapshot_id"]}/predictions'
        ).json()

    with TestClient(database_app(database_url)) as second:
        assert second.get("/ready").json() == {"status": "ready", "storage": "database"}
        twins = second.get("/api/v1/twins").json()
        assert twins["total"] == 1
        assert twins["items"] == [{"twin_id": twin_id, "state_version": 1}]
        assert second.post("/api/v1/twins", json={"twin_id": twin_id}).status_code == 409
        assert second.post(f"/api/v1/twins/{twin_id}/events", json=event).status_code == 409
        state_response = second.get(f"/api/v1/twins/{twin_id}/state")
        assert state_response.status_code == 200
        validate("twin-state", state_response.json())

        audit_response = second.get(f'/api/v1/audits/{prediction["audit_id"]}')
        assert audit_response.status_code == 200
        validate("audit-record", audit_response.json())

        assert second.get(f"/api/v1/twins/{twin_id}/events").json()["total"] == 1
        assert second.get(f"/api/v1/twins/{twin_id}/snapshots").json()["total"] == 1
        assert second.get(f"/api/v1/twins/{twin_id}/predictions").json()["total"] == 1
        assert second.get(f"/api/v1/twins/{twin_id}/audits").json()["total"] == 1

        second_prediction = second.post(
            f'/api/v1/twins/{twin_id}/snapshots/{snapshot["snapshot_id"]}/predictions'
        )
        assert second_prediction.status_code == 201
        validate("prediction", second_prediction.json())

        event["event_id"] = "evt_demo_002"
        stale = second.post(
            f"/api/v1/twins/{twin_id}/events?expected_state_version=0",
            json=event,
        )
        assert stale.status_code == 412
        accepted = second.post(
            f"/api/v1/twins/{twin_id}/events?expected_state_version=1",
            json=event,
        )
        assert accepted.status_code == 201
        assert accepted.json()["state_version"] == 2


@pytest.mark.skipif(not os.environ.get("POSTGRES_TEST_URL"), reason="Requires PostgreSQL")
def test_postgresql_integration_and_concurrency():
    database_url = os.environ.get("POSTGRES_TEST_URL")
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")

    tables = set(inspect(build_engine(database_url)).get_table_names())
    assert "twins" in tables
    assert "clinical_events" in tables

    event = json.loads((ROOT / "contracts/examples/clinical-event.json").read_text())
    twin_id = "pg-twin"
    event["twin_id"] = twin_id

    app = database_app(database_url)
    with TestClient(app) as client:
        client.post("/api/v1/twins", json={"twin_id": twin_id})
        res = client.post(f"/api/v1/twins/{twin_id}/events?expected_state_version=0", json=event)
        assert res.status_code == 201
        
        # Live PostgreSQL testing is delegated to GitHub Actions CI using infra/docker-compose.yml.
        # Persistence check
        state = client.get(f"/api/v1/twins/{twin_id}/state")
        assert state.status_code == 200
        assert state.json()["state_version"] == 1

        # Concurrency check
        event_template = event.copy()
        results = []
        def worker(event_id, expected_version):
            ev = event_template.copy()
            ev["event_id"] = event_id
            response = client.post(f"/api/v1/twins/{twin_id}/events?expected_state_version={expected_version}", json=ev)
            results.append(response.status_code)
            
        t1 = threading.Thread(target=worker, args=("ev_concurrent_1", 1))
        t2 = threading.Thread(target=worker, args=("ev_concurrent_2", 1))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        
        assert 201 in results
        assert (412 in results) or (409 in results)


def test_database_data_foundation_canonical_entities(tmp_path):
    from backend.app.database import create_data_foundation
    database_url = sqlite_url(tmp_path / "foundation.db")
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)

    # Need twin row first due to foreign keys
    stores = create_database_stores(database_url)
    twin_id = "TWIN_DATA_001"
    stores[0].create_twin(twin_id)

    foundation = create_data_foundation(database_url)

    # 1. Patient Profile
    profile = {
        "patient_id": "PAT_001",
        "twin_id": twin_id,
        "gender": "female",
        "birth_date": "1970-05-12",
        "mrn": "MRN-998877",
    }
    saved_prof = foundation.save_patient_profile(profile)
    assert saved_prof["patient_id"] == "PAT_001"
    retrieved_prof = foundation.get_patient_profile(twin_id)
    assert retrieved_prof["mrn"] == "MRN-998877"

    # 2. Tumour Profile
    tumour = {
        "profile_id": "TUM_001",
        "twin_id": twin_id,
        "tumour_size_mm": 22.5,
        "grade": 2,
        "positive_nodes": 1,
        "her2_status": "negative",
        "er_status": "positive",
        "pr_status": "positive",
    }
    foundation.save_tumour_profile(tumour)
    retrieved_tum = foundation.get_tumour_profile(twin_id)
    assert retrieved_tum["tumour_size_mm"] == 22.5
    assert retrieved_tum["grade"] == 2

    # 3. Observation
    obs = {
        "observation_id": "OBS_001",
        "twin_id": twin_id,
        "code": "21889-1",
        "category": "pathology",
        "effective_time": "2026-04-01T10:00:00Z",
        "status": "final",
        "value_numeric": 22.5,
        "unit": "mm",
    }
    foundation.save_observation(obs)
    obs_list = foundation.list_observations(twin_id)
    assert len(obs_list) == 1
    assert obs_list[0]["code"] == "21889-1"

    # 4. Model Version
    model_meta = {
        "model_id": "MOD_001",
        "name": "XGBoost_5yr_Recurrence",
        "version": "1.0.0",
        "algorithm": "XGBClassifier",
        "data_version": "metabric-v1.0.0",
    }
    foundation.register_model_version(model_meta)
    retrieved_mod = foundation.get_model_version("XGBoost_5yr_Recurrence", "1.0.0")
    assert retrieved_mod["algorithm"] == "XGBClassifier"

    # 5. Data Version
    data_meta = {
        "data_version_id": "DV_001",
        "name": "metabric-v1.0.0",
        "dataset_name": "METABRIC",
        "record_count": 1944,
        "content_sha256": "abc123def4567890abcdef1234567890abcdef1234567890abcdef1234567890",
    }
    foundation.register_data_version(data_meta)
    retrieved_dv = foundation.get_data_version("DV_001")
    assert retrieved_dv["record_count"] == 1944


def test_prediction_lineage_query(tmp_path):
    from backend.app.database import create_data_foundation
    database_url = sqlite_url(tmp_path / "lineage.db")
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)

    twin_id = "twin-lineage-01"
    event = json.loads((ROOT / "contracts/examples/clinical-event.json").read_text())
    event["twin_id"] = twin_id

    app = database_app(database_url)
    with TestClient(app) as client:
        client.post("/api/v1/twins", json={"twin_id": twin_id})
        client.post(f"/api/v1/twins/{twin_id}/events", json=event)
        snap = client.post(f"/api/v1/twins/{twin_id}/snapshots").json()
        pred = client.post(
            f"/api/v1/twins/{twin_id}/snapshots/{snap['snapshot_id']}/predictions"
        ).json()
        pred_id = pred["prediction_id"]

    foundation = create_data_foundation(database_url)
    lineage = foundation.get_prediction_lineage(pred_id)
    assert lineage is not None
    assert lineage["prediction"]["prediction_id"] == pred_id
    assert lineage["snapshot"]["snapshot_id"] == snap["snapshot_id"]
    assert len(lineage["referenced_events"]) >= 1
    assert lineage["referenced_events"][0]["event_id"] == event["event_id"]

