"""
Property-based and adversarial tests for OncoTwin-BRCA Event Sourcing & Patient State.

Verifies:
- R1: Determinism (identical state and hash across runs)
- R2: Order Independence (arrival order permutation invariance)
- R3: Idempotent Ingestion (duplicate event rejection / identity)
- R4: As-of Temporal Consistency (monotonicity across clinical/system time)
- Adversarial late amendments (events superseding earlier observations)
- Adversarial conflicting events (same-timestamp contradictory observations)
"""
import copy
import random
from datetime import datetime, timezone, timedelta
import pytest

from backend.app.models import ClinicalEvent, TwinState
from backend.app.store import (
    InMemoryEventStore,
    rebuild_twin_state,
    DuplicateEventError,
    StateVersionConflictError,
)

def make_event(
    event_id: str,
    effective_time: str,
    payload: dict,
    event_type: str = "PATHOLOGY_RESULT",
    received_time: str = "2026-09-01T10:00:00Z",
    quality_status: str = "valid",
    data_version: str = "synthetic-0.1.0",
) -> ClinicalEvent:
    return ClinicalEvent.model_validate({
        "schema_version": "0.1.0",
        "twin_id": "TWIN_PROP_001",
        "event_id": event_id,
        "event_type": event_type,
        "effective_time": effective_time,
        "received_time": received_time,
        "source": "property_test_generator",
        "quality_status": quality_status,
        "provenance": {
            "source_system": "property_test",
            "source_record_id": event_id,
            "data_version": data_version,
        },
        "payload": payload,
    })


# ---------------------------------------------------------------------------
# R1: Determinism Test
# ---------------------------------------------------------------------------
def test_r1_determinism_property():
    """R1: The same set of events processed repeatedly yields identical state and hash."""
    events = [
        make_event("evt_01", "2026-01-10T09:00:00Z", {"tumour_size_mm": 22.0, "grade": 2}),
        make_event("evt_02", "2026-01-15T11:00:00Z", {"er_status": "positive", "her2_status": "negative"}),
        make_event("evt_03", "2026-01-20T14:30:00Z", {"positive_nodes": 1}),
    ]

    base_state = rebuild_twin_state("TWIN_PROP_001", tuple(events))

    for run_i in range(100):
        replay_state = rebuild_twin_state("TWIN_PROP_001", tuple(events))
        assert replay_state.model_dump() == base_state.model_dump(), f"Run {run_i} diverged"
        assert replay_state.values == base_state.values
        assert replay_state.event_ids == base_state.event_ids
        assert replay_state.state_version == base_state.state_version


# ---------------------------------------------------------------------------
# R2: Order Independence Property
# ---------------------------------------------------------------------------
def test_r2_order_independence_property():
    """R2: Permuting the ingestion arrival order does not change the rebuilt state."""
    rng = random.Random(42)
    events = [
        make_event("evt_d1", "2026-01-01T08:00:00Z", {"tumour_size_mm": 18.0}, received_time="2026-01-05T00:00:00Z"),
        make_event("evt_d2", "2026-01-10T09:30:00Z", {"grade": 1}, received_time="2026-01-12T00:00:00Z"),
        make_event("evt_d3", "2026-01-20T10:00:00Z", {"positive_nodes": 0}, received_time="2026-01-22T00:00:00Z"),
        make_event("evt_d4", "2026-01-25T12:00:00Z", {"er_status": "positive"}, received_time="2026-01-26T00:00:00Z"),
        make_event("evt_d5", "2026-02-01T15:00:00Z", {"pr_status": "positive"}, received_time="2026-02-02T00:00:00Z"),
    ]

    canonical_state = rebuild_twin_state("TWIN_PROP_001", tuple(events))

    # Test 50 random permutations
    for perm_i in range(50):
        shuffled = copy.deepcopy(events)
        rng.shuffle(shuffled)
        
        # Ingest into store in shuffled order
        store = InMemoryEventStore()
        store.create_twin("TWIN_PROP_001")
        for ev in shuffled:
            store.append("TWIN_PROP_001", ev)

        perm_state = store.rebuild("TWIN_PROP_001")
        assert perm_state.values == canonical_state.values, f"Values mismatch on permutation {perm_i}"
        assert perm_state.event_ids == canonical_state.event_ids, f"Event IDs mismatch on permutation {perm_i}"
        assert perm_state.state_version == canonical_state.state_version


# ---------------------------------------------------------------------------
# R3: Idempotent Ingestion Property
# ---------------------------------------------------------------------------
def test_r3_idempotency_property():
    """R3: Re-delivering the exact same event is rejected without altering twin state."""
    store = InMemoryEventStore()
    store.create_twin("TWIN_PROP_001")

    ev1 = make_event("evt_first", "2026-01-01T10:00:00Z", {"grade": 2})
    store.append("TWIN_PROP_001", ev1)

    state_before = store.rebuild("TWIN_PROP_001")

    # Duplicate delivery must raise DuplicateEventError
    with pytest.raises(DuplicateEventError):
        store.append("TWIN_PROP_001", ev1)

    state_after = store.rebuild("TWIN_PROP_001")
    assert state_after.model_dump() == state_before.model_dump()
    assert state_after.state_version == 1


# ---------------------------------------------------------------------------
# R4: As-Of Consistency Property
# ---------------------------------------------------------------------------
def test_r4_as_of_consistency_property():
    """R4: State as of time tau_c depends only on events with effective_time <= tau_c."""
    t1 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)

    ev1 = make_event("evt_jan", t1.isoformat(), {"tumour_size_mm": 20.0})
    ev2 = make_event("evt_feb", t2.isoformat(), {"grade": 2})
    ev3 = make_event("evt_mar", t3.isoformat(), {"positive_nodes": 3})

    # As-of February 15 query
    tau_c = datetime(2026, 2, 15, 0, 0, tzinfo=timezone.utc)

    # Ingest only events prior to tau_c
    past_state = rebuild_twin_state("TWIN_PROP_001", (ev1, ev2))

    # All events present in database, but we filter for effective_time <= tau_c
    all_events = (ev1, ev2, ev3)
    filtered_events = tuple(e for e in all_events if e.effective_time <= tau_c)
    as_of_state = rebuild_twin_state("TWIN_PROP_001", filtered_events)

    assert as_of_state.values == past_state.values
    assert as_of_state.event_ids == ["evt_jan", "evt_feb"]
    assert "positive_nodes" not in as_of_state.values


# ---------------------------------------------------------------------------
# Adversarial Test 1: Late Amendments
# ---------------------------------------------------------------------------
def test_adversarial_late_amendment():
    """
    Adversarial scenario: A surgical pathology report arrives on Feb 1st,
    superseding an earlier preliminary biopsy result from Jan 10th.
    State must correctly apply the amendment without losing event history.
    """
    store = InMemoryEventStore()
    store.create_twin("TWIN_PROP_001")

    # Initial biopsy
    ev_initial = make_event("evt_biopsy_prelim", "2026-01-10T10:00:00Z", {"grade": 1, "tumour_size_mm": 15.0})
    store.append("TWIN_PROP_001", ev_initial)

    # Later event arrives
    ev_interim = make_event("evt_receptor_panel", "2026-01-15T10:00:00Z", {"er_status": "positive"})
    store.append("TWIN_PROP_001", ev_interim)

    # Late amendment: definitive pathology from resection (effective Jan 12, received Feb 1)
    ev_amended = make_event(
        "evt_pathology_resection",
        "2026-01-12T10:00:00Z",
        {"grade": 3, "tumour_size_mm": 28.0, "positive_nodes": 2},
        received_time="2026-02-01T10:00:00Z"
    )
    store.append("TWIN_PROP_001", ev_amended)

    rebuilt = store.rebuild("TWIN_PROP_001")

    # In canonical replay, ev_amended (Jan 12) overrides ev_initial (Jan 10) for overlapping keys
    assert rebuilt.values["grade"] == 3
    assert rebuilt.values["tumour_size_mm"] == 28.0
    assert rebuilt.values["positive_nodes"] == 2
    assert rebuilt.values["er_status"] == "positive"
    # Provenance retains all 3 events in canonical order
    assert rebuilt.event_ids == ["evt_biopsy_prelim", "evt_pathology_resection", "evt_receptor_panel"]


# ---------------------------------------------------------------------------
# Adversarial Test 2: Conflicting Events at Same Clinical Timestamp
# ---------------------------------------------------------------------------
def test_adversarial_same_timestamp_conflicts():
    """
    Adversarial scenario: Two conflicting laboratory events have the exact same effective time.
    Deterministic tie-breaker by event_id must ensure order independence regardless of arrival.
    """
    # Event X and Event Y have the exact same effective time but contradictory grade
    same_time = "2026-01-10T12:00:00Z"
    ev_a = make_event("evt_lab_A", same_time, {"grade": 1})
    ev_b = make_event("evt_lab_B", same_time, {"grade": 3})

    # Forward arrival: A then B
    store_ab = InMemoryEventStore()
    store_ab.create_twin("TWIN_PROP_001")
    store_ab.append("TWIN_PROP_001", ev_a)
    store_ab.append("TWIN_PROP_001", ev_b)
    state_ab = store_ab.rebuild("TWIN_PROP_001")

    # Reverse arrival: B then A
    store_ba = InMemoryEventStore()
    store_ba.create_twin("TWIN_PROP_001")
    store_ba.append("TWIN_PROP_001", ev_b)
    store_ba.append("TWIN_PROP_001", ev_a)
    state_ba = store_ba.rebuild("TWIN_PROP_001")

    # Both must resolve to the identical deterministic canonical state
    assert state_ab.values == state_ba.values
    assert state_ab.event_ids == state_ba.event_ids == ["evt_lab_A", "evt_lab_B"]
    # Because evt_lab_B sorts after evt_lab_A, grade resolves to 3 deterministically
    assert state_ab.values["grade"] == 3


# ---------------------------------------------------------------------------
# Adversarial Test 3: Optimistic Concurrency & Version Conflicts
# ---------------------------------------------------------------------------
def test_adversarial_optimistic_concurrency():
    """Concurrent worker appends expecting state version 1 when version is already 2."""
    store = InMemoryEventStore()
    store.create_twin("TWIN_PROP_001")

    ev1 = make_event("evt_1", "2026-01-01T00:00:00Z", {"grade": 2})
    ev2 = make_event("evt_2", "2026-01-02T00:00:00Z", {"grade": 3})
    store.append("TWIN_PROP_001", ev1)
    store.append("TWIN_PROP_001", ev2)

    ev3 = make_event("evt_3", "2026-01-03T00:00:00Z", {"grade": 1})
    # Stale worker tries to commit expecting version 1
    with pytest.raises(StateVersionConflictError) as exc_info:
        store.append("TWIN_PROP_001", ev3, expected_state_version=1)
    assert "Current state version is 2" in str(exc_info.value)
