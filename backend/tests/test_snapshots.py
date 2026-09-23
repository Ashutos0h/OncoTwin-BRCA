from datetime import datetime, timezone
from uuid import UUID

import pytest

from backend.app.models import TwinState
from backend.app.snapshots import InMemorySnapshotStore, SnapshotNotFoundError


def state() -> TwinState:
    return TwinState(
        schema_version="0.1.0",
        twin_id="twin-1",
        state_version=2,
        as_of="2026-09-02T10:00:00Z",
        event_ids=["event-1", "event-2"],
        data_version="data-v1",
        values={"grade": 2, "her2_status": None},
        missing_fields=["her2_status"],
        quality_warnings=[],
    )


def test_snapshot_is_deterministic_with_injected_identity_and_clock():
    store = InMemorySnapshotStore(
        clock=lambda: datetime(2026, 9, 3, tzinfo=timezone.utc),
        id_factory=lambda: UUID("00000000-0000-0000-0000-000000000001"),
    )
    snapshot = store.create(state())
    assert snapshot.snapshot_id == "snapshot_00000000000000000000000000000001"
    assert snapshot.created_at == datetime(2026, 9, 3, tzinfo=timezone.utc)
    assert snapshot.state_version == 2
    assert snapshot.features == {"grade": 2, "her2_status": None}
    assert store.get(snapshot.snapshot_id) == snapshot


def test_stored_snapshot_is_isolated_from_returned_data():
    store = InMemorySnapshotStore()
    snapshot = store.create(state())
    snapshot.features["grade"] = 99
    assert store.get(snapshot.snapshot_id).features["grade"] == 2


def test_unknown_snapshot_is_rejected():
    with pytest.raises(SnapshotNotFoundError):
        InMemorySnapshotStore().get("missing")


def test_naive_snapshot_clock_is_rejected():
    store = InMemorySnapshotStore(clock=lambda: datetime(2026, 9, 3))
    with pytest.raises(ValueError, match="timezone-aware"):
        store.create(state())
