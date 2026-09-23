"""Feature-snapshot creation and in-memory persistence."""

from collections.abc import Callable
from datetime import datetime, timezone
from threading import RLock
from uuid import UUID, uuid4

from backend.app.models import FeatureSnapshot, TwinState


class SnapshotNotFoundError(Exception):
    pass


class InMemorySnapshotStore:
    """Create immutable feature snapshots from reconstructed twin states."""

    def __init__(
        self,
        *,
        feature_set_version: str = "demo-0.1.0",
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], UUID] | None = None,
    ) -> None:
        self._feature_set_version = feature_set_version
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or uuid4
        self._snapshots: dict[str, str] = {}
        self._event_ids: dict[str, tuple[str, ...]] = {}
        self._lock = RLock()

    def create(self, state: TwinState) -> FeatureSnapshot:
        created_at = self._clock()
        if created_at.utcoffset() is None:
            raise ValueError("Snapshot clock must return a timezone-aware datetime.")

        snapshot = FeatureSnapshot(
            schema_version="0.1.0",
            twin_id=state.twin_id,
            snapshot_id=f"snapshot_{self._id_factory().hex}",
            state_version=state.state_version,
            created_at=created_at,
            data_version=state.data_version,
            feature_set_version=self._feature_set_version,
            features=state.values,
            missing_fields=state.missing_fields,
        )
        serialized = snapshot.model_dump_json()
        with self._lock:
            self._snapshots[snapshot.snapshot_id] = serialized
            self._event_ids[snapshot.snapshot_id] = tuple(state.event_ids)
        return FeatureSnapshot.model_validate_json(serialized)

    def get(self, snapshot_id: str) -> FeatureSnapshot:
        with self._lock:
            try:
                serialized = self._snapshots[snapshot_id]
            except KeyError:
                raise SnapshotNotFoundError(snapshot_id) from None
        return FeatureSnapshot.model_validate_json(serialized)

    def event_ids_for(self, snapshot_id: str) -> tuple[str, ...]:
        with self._lock:
            try:
                return self._event_ids[snapshot_id]
            except KeyError:
                raise SnapshotNotFoundError(snapshot_id) from None

    def list_for(
        self, twin_id: str, *, limit: int, offset: int
    ) -> tuple[list[FeatureSnapshot], int]:
        with self._lock:
            snapshots = [
                FeatureSnapshot.model_validate_json(value)
                for value in self._snapshots.values()
            ]
        matching = sorted(
            (item for item in snapshots if item.twin_id == twin_id),
            key=lambda item: (item.created_at, item.snapshot_id),
            reverse=True,
        )
        return matching[offset : offset + limit], len(matching)
