from datetime import datetime, timezone

from backend.app.models import ClinicalEvent
from backend.app.store import InMemoryEventStore


def make_event(event_id: str, effective_time: str, payload: dict, data_version: str) -> ClinicalEvent:
    return ClinicalEvent.model_validate(
        {
            "schema_version": "0.1.0",
            "twin_id": "twin-1",
            "event_id": event_id,
            "event_type": "FOLLOW_UP",
            "effective_time": effective_time,
            "received_time": "2026-09-03T00:00:00Z",
            "source": "synthetic-test",
            "quality_status": "valid",
            "provenance": {
                "source_system": "test",
                "source_record_id": event_id,
                "data_version": data_version,
            },
            "payload": payload,
        }
    )


def build(events: list[ClinicalEvent]):
    store = InMemoryEventStore()
    store.create_twin("twin-1")
    for event in events:
        store.append("twin-1", event)
    return store.rebuild("twin-1")


def test_out_of_order_events_replay_deterministically():
    early = make_event("event-a", "2026-09-01T00:00:00Z", {"grade": 2, "marker": None}, "data-v1")
    late = make_event("event-b", "2026-09-02T00:00:00Z", {"grade": 3}, "data-v2")

    forward = build([early, late])
    reverse = build([late, early])

    assert forward == reverse
    assert forward.event_ids == ["event-a", "event-b"]
    assert forward.values == {"grade": 3, "marker": None}
    assert forward.missing_fields == ["marker"]
    assert forward.data_version == "data-v2"
    assert forward.as_of == datetime(2026, 9, 2, tzinfo=timezone.utc)


def test_same_time_tie_breaker_uses_event_id():
    event_b = make_event("event-b", "2026-09-01T00:00:00Z", {"grade": 3}, "data-v1")
    event_a = make_event("event-a", "2026-09-01T00:00:00Z", {"grade": 2}, "data-v1")
    state = build([event_b, event_a])
    assert state.event_ids == ["event-a", "event-b"]
    assert state.values["grade"] == 3


def test_stored_event_is_isolated_from_caller_mutation():
    event = make_event("event-a", "2026-09-01T00:00:00Z", {"grade": 2}, "data-v1")
    store = InMemoryEventStore()
    store.create_twin("twin-1")
    store.append("twin-1", event)

    event.payload["grade"] = 99
    assert store.rebuild("twin-1").values["grade"] == 2

