import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.store import InMemoryEventStore, StorageUnavailableError
from scripts.validate_contracts import validate


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def event() -> dict:
    return json.loads((ROOT / "contracts/examples/clinical-event.json").read_text())


def create_twin(client: TestClient, twin_id: str) -> None:
    response = client.post("/api/v1/twins", json={"twin_id": twin_id})
    assert response.status_code == 201


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "oncotwin-backend",
        "mode": "in-memory",
    }
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "storage": "in-memory"}


def test_readiness_returns_503_when_storage_is_unavailable():
    class UnavailableStore(InMemoryEventStore):
        def check_ready(self) -> None:
            raise StorageUnavailableError()

    response = TestClient(create_app(store=UnavailableStore())).get("/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Storage unavailable."}


def test_expected_errors_are_documented(client: TestClient):
    paths = client.get("/openapi.json").json()["paths"]
    assert "409" in paths["/api/v1/twins"]["post"]["responses"]
    assert "404" in paths["/api/v1/twins/{twin_id}/events"]["post"]["responses"]
    assert "409" in paths["/api/v1/twins/{twin_id}/events"]["post"]["responses"]
    assert "412" in paths["/api/v1/twins/{twin_id}/events"]["post"]["responses"]
    assert "503" in paths["/ready"]["get"]["responses"]
    assert "404" in paths["/api/v1/twins/{twin_id}/state"]["get"]["responses"]
    assert "409" in paths["/api/v1/twins/{twin_id}/state"]["get"]["responses"]
    assert "404" in paths["/api/v1/twins/{twin_id}/snapshots"]["post"]["responses"]
    assert "409" in paths["/api/v1/twins/{twin_id}/snapshots"]["post"]["responses"]
    prediction_path = "/api/v1/twins/{twin_id}/snapshots/{snapshot_id}/predictions"
    assert "404" in paths[prediction_path]["post"]["responses"]
    assert "404" in paths["/api/v1/audits/{audit_id}"]["get"]["responses"]
    assert "/api/v1/twins/{twin_id}/events" in paths
    assert "/api/v1/twins/{twin_id}/snapshots" in paths
    assert "/api/v1/twins/{twin_id}/predictions" in paths
    assert "/api/v1/twins/{twin_id}/audits" in paths
    assert "/api/v1/predictions/{prediction_id}" in paths


def test_create_twin_and_reject_duplicate(client: TestClient):
    response = client.post("/api/v1/twins", json={"twin_id": "twin-1"})
    assert response.status_code == 201
    assert response.json() == {"twin_id": "twin-1", "status": "created"}
    assert client.post("/api/v1/twins", json={"twin_id": "twin-1"}).status_code == 409


def test_list_twins_is_sorted_and_paginated(client: TestClient):
    create_twin(client, "twin-b")
    create_twin(client, "twin-a")
    response = client.get("/api/v1/twins?limit=1&offset=0")
    assert response.status_code == 200
    assert response.json() == {
        "items": [{"twin_id": "twin-a", "state_version": 0}],
        "total": 2,
        "limit": 1,
        "offset": 0,
    }


def test_api_key_roles_and_openapi_security():
    secured = TestClient(
        create_app(
            auth_enabled=True,
            reader_api_key="reader-secret",
            writer_api_key="writer-secret",
        )
    )
    assert secured.get("/health").status_code == 200
    assert secured.get("/api/v1/twins").status_code == 401
    reader_headers = {"X-API-Key": "reader-secret"}
    writer_headers = {"X-API-Key": "writer-secret"}
    assert secured.post(
        "/api/v1/twins", json={"twin_id": "secured"}, headers=reader_headers
    ).status_code == 403
    assert secured.post(
        "/api/v1/twins", json={"twin_id": "secured"}, headers=writer_headers
    ).status_code == 201
    assert secured.get("/api/v1/twins", headers=reader_headers).status_code == 200
    assert secured.get("/api/v1/twins", headers=writer_headers).status_code == 200

    document = secured.get("/openapi.json").json()
    assert "OncoTwinApiKey" in document["components"]["securitySchemes"]
    assert document["paths"]["/api/v1/twins"]["post"]["security"]


def test_request_id_is_propagated_and_invalid_value_is_replaced(client: TestClient):
    response = client.get("/health", headers={"X-Request-ID": "demo-request-1"})
    assert response.headers["x-request-id"] == "demo-request-1"
    assert float(response.headers["x-process-time-ms"]) >= 0

    replaced = client.get("/health", headers={"X-Request-ID": "unsafe value"})
    assert replaced.headers["x-request-id"] != "unsafe value"
    assert len(replaced.headers["x-request-id"]) == 32


def test_unknown_and_empty_twin_states(client: TestClient):
    assert client.get("/api/v1/twins/missing/state").status_code == 404
    create_twin(client, "empty")
    assert client.get("/api/v1/twins/empty/state").status_code == 409


def test_accept_event_and_rebuild_state(client: TestClient, event: dict):
    create_twin(client, event["twin_id"])
    accepted = client.post(f'/api/v1/twins/{event["twin_id"]}/events', json=event)
    assert accepted.status_code == 201
    assert accepted.json() == {
        "twin_id": event["twin_id"],
        "event_id": event["event_id"],
        "status": "accepted",
        "state_version": 1,
    }

    state = client.get(f'/api/v1/twins/{event["twin_id"]}/state')
    assert state.status_code == 200
    body = state.json()
    assert body["event_ids"] == [event["event_id"]]
    assert body["values"] == event["payload"]
    assert body["missing_fields"] == ["her2_status"]
    assert body["data_version"] == event["provenance"]["data_version"]
    assert state.headers["etag"] == '"1"'
    validate("twin-state", body)


def test_expected_state_version_prevents_stale_event_write(client: TestClient, event: dict):
    twin_id = event["twin_id"]
    create_twin(client, twin_id)
    first = client.post(
        f"/api/v1/twins/{twin_id}/events?expected_state_version=0",
        json=event,
    )
    assert first.status_code == 201
    assert first.json()["state_version"] == 1

    event["event_id"] = "evt_demo_002"
    stale = client.post(
        f"/api/v1/twins/{twin_id}/events?expected_state_version=0",
        json=event,
    )
    assert stale.status_code == 412
    assert stale.json() == {
        "detail": "State version conflict. Current version is 1."
    }
    assert client.get(f"/api/v1/twins/{twin_id}/state").json()["state_version"] == 1

    retry = client.post(
        f"/api/v1/twins/{twin_id}/events?expected_state_version=1",
        json=event,
    )
    assert retry.status_code == 201
    assert retry.json()["state_version"] == 2


def test_reject_duplicate_event_id_globally(client: TestClient, event: dict):
    create_twin(client, event["twin_id"])
    create_twin(client, "another-twin")
    assert client.post(f'/api/v1/twins/{event["twin_id"]}/events', json=event).status_code == 201
    event["twin_id"] = "another-twin"
    response = client.post("/api/v1/twins/another-twin/events", json=event)
    assert response.status_code == 409


def test_reject_path_mismatch_and_invalid_quality(client: TestClient, event: dict):
    create_twin(client, event["twin_id"])
    mismatch = client.post("/api/v1/twins/different/events", json=event)
    assert mismatch.status_code == 422

    event["quality_status"] = "invalid"
    invalid = client.post(f'/api/v1/twins/{event["twin_id"]}/events', json=event)
    assert invalid.status_code == 422
    assert client.get(f'/api/v1/twins/{event["twin_id"]}/state').status_code == 409


def test_contract_validation_rejects_extra_fields(client: TestClient, event: dict):
    create_twin(client, event["twin_id"])
    event["unexpected"] = True
    assert client.post(f'/api/v1/twins/{event["twin_id"]}/events', json=event).status_code == 422


def test_create_feature_snapshot_with_state_lineage(client: TestClient, event: dict):
    create_twin(client, event["twin_id"])
    client.post(f'/api/v1/twins/{event["twin_id"]}/events', json=event)

    response = client.post(f'/api/v1/twins/{event["twin_id"]}/snapshots')
    assert response.status_code == 201
    snapshot = response.json()
    validate("feature-snapshot", snapshot)
    assert snapshot["twin_id"] == event["twin_id"]
    assert snapshot["state_version"] == 1
    assert snapshot["data_version"] == event["provenance"]["data_version"]
    assert snapshot["features"] == event["payload"]
    assert snapshot["missing_fields"] == ["her2_status"]
    assert snapshot["feature_set_version"] == "demo-0.1.0"
    assert snapshot["snapshot_id"].startswith("snapshot_")


def test_snapshot_requires_existing_nonempty_twin(client: TestClient):
    assert client.post("/api/v1/twins/missing/snapshots").status_code == 404
    create_twin(client, "empty")
    assert client.post("/api/v1/twins/empty/snapshots").status_code == 409


def test_prediction_and_audit_preserve_complete_lineage(client: TestClient, event: dict):
    twin_id = event["twin_id"]
    create_twin(client, twin_id)
    client.post(f"/api/v1/twins/{twin_id}/events", json=event)
    snapshot = client.post(f"/api/v1/twins/{twin_id}/snapshots").json()

    prediction_response = client.post(
        f'/api/v1/twins/{twin_id}/snapshots/{snapshot["snapshot_id"]}/predictions'
    )
    assert prediction_response.status_code == 201
    prediction = prediction_response.json()
    validate("prediction", prediction)
    assert prediction["twin_id"] == twin_id
    assert prediction["snapshot_id"] == snapshot["snapshot_id"]
    assert prediction["state_version"] == snapshot["state_version"]
    assert prediction["data_version"] == snapshot["data_version"]
    assert prediction["is_mock"] is True
    assert prediction["confidence"] == "not_assessed"

    audit_response = client.get(f'/api/v1/audits/{prediction["audit_id"]}')
    assert audit_response.status_code == 200
    audit = audit_response.json()
    validate("audit-record", audit)
    assert audit["audit_id"] == prediction["audit_id"]
    assert audit["prediction_id"] == prediction["prediction_id"]
    assert audit["snapshot_id"] == snapshot["snapshot_id"]
    assert audit["event_ids"] == [event["event_id"]]
    assert audit["state_version"] == snapshot["state_version"]
    assert audit["model_version"] == prediction["model_version"]
    assert audit["data_version"] == snapshot["data_version"]


def test_prediction_rejects_unknown_or_wrong_twin_snapshot(client: TestClient, event: dict):
    twin_id = event["twin_id"]
    create_twin(client, twin_id)
    client.post(f"/api/v1/twins/{twin_id}/events", json=event)
    snapshot = client.post(f"/api/v1/twins/{twin_id}/snapshots").json()
    assert client.post(f"/api/v1/twins/{twin_id}/snapshots/missing/predictions").status_code == 404
    response = client.post(
        f'/api/v1/twins/other/snapshots/{snapshot["snapshot_id"]}/predictions'
    )
    assert response.status_code == 404


def test_unknown_audit_returns_404(client: TestClient):
    assert client.get("/api/v1/audits/missing").status_code == 404


def test_paginated_twin_history_and_prediction_lookup(client: TestClient, event: dict):
    twin_id = event["twin_id"]
    create_twin(client, twin_id)
    client.post(f"/api/v1/twins/{twin_id}/events", json=event)
    first_snapshot = client.post(f"/api/v1/twins/{twin_id}/snapshots").json()
    first_prediction = client.post(
        f'/api/v1/twins/{twin_id}/snapshots/{first_snapshot["snapshot_id"]}/predictions'
    ).json()

    event["event_id"] = "evt_demo_002"
    event["effective_time"] = "2026-09-02T10:00:00Z"
    event["received_time"] = "2026-09-02T10:05:00Z"
    event["payload"] = {"her2_status": "negative"}
    event["quality_status"] = "valid"
    client.post(f"/api/v1/twins/{twin_id}/events", json=event)
    second_snapshot = client.post(f"/api/v1/twins/{twin_id}/snapshots").json()
    client.post(
        f'/api/v1/twins/{twin_id}/snapshots/{second_snapshot["snapshot_id"]}/predictions'
    )

    events = client.get(f"/api/v1/twins/{twin_id}/events?limit=1&offset=1").json()
    assert events["total"] == 2
    assert events["limit"] == 1
    assert events["offset"] == 1
    assert [item["event_id"] for item in events["items"]] == ["evt_demo_002"]

    for resource in ("snapshots", "predictions", "audits"):
        page = client.get(f"/api/v1/twins/{twin_id}/{resource}?limit=1").json()
        assert page["total"] == 2
        assert len(page["items"]) == 1

    fetched = client.get(f'/api/v1/predictions/{first_prediction["prediction_id"]}')
    assert fetched.status_code == 200
    assert fetched.json() == first_prediction


def test_history_requires_twin_and_valid_pagination(client: TestClient):
    for resource in ("events", "snapshots", "predictions", "audits"):
        assert client.get(f"/api/v1/twins/missing/{resource}").status_code == 404
    create_twin(client, "empty")
    assert client.get("/api/v1/twins/empty/events?limit=0").status_code == 422
    assert client.get("/api/v1/twins/empty/events?limit=201").status_code == 422
    assert client.get("/api/v1/twins/empty/events?offset=-1").status_code == 422
    assert client.get("/api/v1/predictions/missing").status_code == 404


def test_frontend_origin_is_allowed_by_cors(client: TestClient):
    response = client.options(
        "/api/v1/twins",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
