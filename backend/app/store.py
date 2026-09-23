"""Thread-safe in-memory event store and deterministic twin replay."""

from collections import defaultdict
from threading import RLock

from backend.app.models import ClinicalEvent, TwinState, TwinSummary


class TwinAlreadyExistsError(Exception):
    pass


class TwinNotFoundError(Exception):
    pass


class DuplicateEventError(Exception):
    pass


class EmptyTwinError(Exception):
    pass


class InvalidQualityEventError(Exception):
    pass


class StateVersionConflictError(Exception):
    def __init__(self, current_version: int) -> None:
        self.current_version = current_version
        super().__init__(f"Current state version is {current_version}.")


class StorageUnavailableError(Exception):
    pass


def rebuild_twin_state(twin_id: str, events: tuple[ClinicalEvent, ...]) -> TwinState:
    ordered = sorted(
        events,
        key=lambda event: (event.effective_time, event.received_time, event.event_id),
    )
    if not ordered:
        raise EmptyTwinError(twin_id)

    values = {}
    warnings = []
    for event in ordered:
        values.update(event.payload)
        if event.quality_status == "warning":
            warnings.append(f"Event {event.event_id} has warning quality status.")

    latest = ordered[-1]
    return TwinState(
        schema_version="0.1.0",
        twin_id=twin_id,
        state_version=len(ordered),
        as_of=latest.effective_time,
        event_ids=[event.event_id for event in ordered],
        data_version=latest.provenance.data_version,
        values=values,
        missing_fields=sorted(key for key, value in values.items() if value is None),
        quality_warnings=warnings,
    )


class InMemoryEventStore:
    """Store canonical event JSON so saved events cannot be mutated by callers."""

    def __init__(self) -> None:
        self._twins: set[str] = set()
        self._events_by_twin: dict[str, list[str]] = defaultdict(list)
        self._event_ids: set[str] = set()
        self._lock = RLock()

    def create_twin(self, twin_id: str) -> None:
        with self._lock:
            if twin_id in self._twins:
                raise TwinAlreadyExistsError(twin_id)
            self._twins.add(twin_id)

    def append(
        self,
        twin_id: str,
        event: ClinicalEvent,
        expected_state_version: int | None = None,
    ) -> int:
        with self._lock:
            if twin_id not in self._twins:
                raise TwinNotFoundError(twin_id)
            current_version = len(self._events_by_twin[twin_id])
            if (
                expected_state_version is not None
                and expected_state_version != current_version
            ):
                raise StateVersionConflictError(current_version)
            if event.quality_status == "invalid":
                raise InvalidQualityEventError(event.event_id)
            if event.event_id in self._event_ids:
                raise DuplicateEventError(event.event_id)

            self._events_by_twin[twin_id].append(event.model_dump_json())
            self._event_ids.add(event.event_id)
            return len(self._events_by_twin[twin_id])

    def check_ready(self) -> None:
        return None

    def list_twins(self, *, limit: int, offset: int) -> tuple[list[TwinSummary], int]:
        with self._lock:
            items = [
                TwinSummary(
                    twin_id=twin_id,
                    state_version=len(self._events_by_twin[twin_id]),
                )
                for twin_id in sorted(self._twins)
            ]
        return items[offset : offset + limit], len(items)

    def events_for(self, twin_id: str) -> tuple[ClinicalEvent, ...]:
        with self._lock:
            if twin_id not in self._twins:
                raise TwinNotFoundError(twin_id)
            return tuple(
                ClinicalEvent.model_validate_json(serialized)
                for serialized in self._events_by_twin[twin_id]
            )

    def rebuild(self, twin_id: str) -> TwinState:
        return rebuild_twin_state(twin_id, self.events_for(twin_id))

    def list_for(
        self, twin_id: str, *, limit: int, offset: int
    ) -> tuple[list[ClinicalEvent], int]:
        ordered = sorted(
            self.events_for(twin_id),
            key=lambda item: (item.effective_time, item.received_time, item.event_id),
        )
        return ordered[offset : offset + limit], len(ordered)
