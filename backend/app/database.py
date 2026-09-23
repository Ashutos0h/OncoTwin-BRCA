"""SQLAlchemy persistence for twins, events, snapshots, predictions, and audits."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from backend.app.inference import InferenceEngine, MockInferenceEngine
from backend.app.models import (
    AuditRecord,
    ClinicalEvent,
    FeatureSnapshot,
    Prediction,
    TwinState,
    TwinSummary,
)
from backend.app.results import AuditNotFoundError, PredictionNotFoundError
from backend.app.snapshots import SnapshotNotFoundError
from backend.app.store import (
    DuplicateEventError,
    InvalidQualityEventError,
    TwinAlreadyExistsError,
    TwinNotFoundError,
    StateVersionConflictError,
    StorageUnavailableError,
    rebuild_twin_state,
)


JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class TwinRow(Base):
    __tablename__ = "twins"
    twin_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ClinicalEventRow(Base):
    __tablename__ = "clinical_events"
    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    twin_id: Mapped[str] = mapped_column(ForeignKey("twins.twin_id"), nullable=False)
    effective_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    __table_args__ = (Index("ix_clinical_events_twin_id", "twin_id"),)


class FeatureSnapshotRow(Base):
    __tablename__ = "feature_snapshots"
    snapshot_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    twin_id: Mapped[str] = mapped_column(ForeignKey("twins.twin_id"), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_ids: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    __table_args__ = (Index("ix_feature_snapshots_twin_id", "twin_id"),)


class PredictionRow(Base):
    __tablename__ = "predictions"
    prediction_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    twin_id: Mapped[str] = mapped_column(ForeignKey("twins.twin_id"), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("feature_snapshots.snapshot_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    __table_args__ = (Index("ix_predictions_twin_id", "twin_id"),)


class AuditRecordRow(Base):
    __tablename__ = "audit_records"
    audit_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    twin_id: Mapped[str] = mapped_column(ForeignKey("twins.twin_id"), nullable=False)
    prediction_id: Mapped[str] = mapped_column(
        ForeignKey("predictions.prediction_id"), nullable=False, unique=True
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    __table_args__ = (Index("ix_audit_records_twin_id", "twin_id"),)


SessionFactory = sessionmaker[Session]


def build_engine(database_url: str) -> Engine:
    options = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, pool_pre_ping=True, connect_args=options)
    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def build_session_factory(engine: Engine) -> SessionFactory:
    return sessionmaker(bind=engine, expire_on_commit=False)


class DatabaseEventStore:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def create_twin(self, twin_id: str) -> None:
        with self._sessions() as session:
            session.add(
                TwinRow(
                    twin_id=twin_id,
                    created_at=datetime.now(timezone.utc),
                    state_version=0,
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise TwinAlreadyExistsError(twin_id) from None

    def append(
        self,
        twin_id: str,
        event: ClinicalEvent,
        expected_state_version: int | None = None,
    ) -> int:
        if event.quality_status == "invalid":
            raise InvalidQualityEventError(event.event_id)
        with self._sessions() as session:
            twin = session.scalar(
                select(TwinRow)
                .where(TwinRow.twin_id == twin_id)
                .with_for_update()
            )
            if twin is None:
                raise TwinNotFoundError(twin_id)
            if (
                expected_state_version is not None
                and expected_state_version != twin.state_version
            ):
                raise StateVersionConflictError(twin.state_version)
            session.add(
                ClinicalEventRow(
                    event_id=event.event_id,
                    twin_id=twin_id,
                    effective_time=event.effective_time,
                    received_time=event.received_time,
                    document=event.model_dump(mode="json"),
                )
            )
            twin.state_version += 1
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                raise DuplicateEventError(event.event_id) from None
            return twin.state_version

    def check_ready(self) -> None:
        try:
            with self._sessions() as session:
                session.execute(select(TwinRow.twin_id).limit(1))
        except SQLAlchemyError as error:
            raise StorageUnavailableError("Database storage is unavailable.") from error

    def list_twins(self, *, limit: int, offset: int) -> tuple[list[TwinSummary], int]:
        with self._sessions() as session:
            total = session.scalar(select(func.count()).select_from(TwinRow)) or 0
            rows = session.scalars(
                select(TwinRow).order_by(TwinRow.twin_id).offset(offset).limit(limit)
            ).all()
            return [
                TwinSummary(twin_id=row.twin_id, state_version=row.state_version)
                for row in rows
            ], total

    def events_for(self, twin_id: str) -> tuple[ClinicalEvent, ...]:
        with self._sessions() as session:
            if session.get(TwinRow, twin_id) is None:
                raise TwinNotFoundError(twin_id)
            rows = session.scalars(
                select(ClinicalEventRow)
                .where(ClinicalEventRow.twin_id == twin_id)
                .order_by(
                    ClinicalEventRow.effective_time,
                    ClinicalEventRow.received_time,
                    ClinicalEventRow.event_id,
                )
            ).all()
            return tuple(ClinicalEvent.model_validate(row.document) for row in rows)

    def rebuild(self, twin_id: str) -> TwinState:
        return rebuild_twin_state(twin_id, self.events_for(twin_id))

    def list_for(
        self, twin_id: str, *, limit: int, offset: int
    ) -> tuple[list[ClinicalEvent], int]:
        with self._sessions() as session:
            if session.get(TwinRow, twin_id) is None:
                raise TwinNotFoundError(twin_id)
            where = ClinicalEventRow.twin_id == twin_id
            total = session.scalar(
                select(func.count()).select_from(ClinicalEventRow).where(where)
            ) or 0
            rows = session.scalars(
                select(ClinicalEventRow)
                .where(where)
                .order_by(
                    ClinicalEventRow.effective_time,
                    ClinicalEventRow.received_time,
                    ClinicalEventRow.event_id,
                )
                .offset(offset)
                .limit(limit)
            ).all()
            return [ClinicalEvent.model_validate(row.document) for row in rows], total


class DatabaseSnapshotStore:
    def __init__(
        self,
        sessions: SessionFactory,
        *,
        feature_set_version: str = "demo-0.1.0",
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], UUID] | None = None,
    ) -> None:
        self._sessions = sessions
        self._feature_set_version = feature_set_version
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or uuid4

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
        with self._sessions() as session:
            session.add(
                FeatureSnapshotRow(
                    snapshot_id=snapshot.snapshot_id,
                    twin_id=snapshot.twin_id,
                    state_version=snapshot.state_version,
                    created_at=snapshot.created_at,
                    event_ids=list(state.event_ids),
                    document=snapshot.model_dump(mode="json"),
                )
            )
            session.commit()
        return snapshot.model_copy(deep=True)

    def _row(self, snapshot_id: str) -> FeatureSnapshotRow:
        with self._sessions() as session:
            row = session.get(FeatureSnapshotRow, snapshot_id)
            if row is None:
                raise SnapshotNotFoundError(snapshot_id)
            session.expunge(row)
            return row

    def get(self, snapshot_id: str) -> FeatureSnapshot:
        return FeatureSnapshot.model_validate(self._row(snapshot_id).document)

    def event_ids_for(self, snapshot_id: str) -> tuple[str, ...]:
        return tuple(self._row(snapshot_id).event_ids)

    def list_for(
        self, twin_id: str, *, limit: int, offset: int
    ) -> tuple[list[FeatureSnapshot], int]:
        with self._sessions() as session:
            where = FeatureSnapshotRow.twin_id == twin_id
            total = session.scalar(
                select(func.count()).select_from(FeatureSnapshotRow).where(where)
            ) or 0
            rows = session.scalars(
                select(FeatureSnapshotRow)
                .where(where)
                .order_by(
                    FeatureSnapshotRow.created_at.desc(),
                    FeatureSnapshotRow.snapshot_id.desc(),
                )
                .offset(offset)
                .limit(limit)
            ).all()
            return [FeatureSnapshot.model_validate(row.document) for row in rows], total


class DatabasePredictionAuditStore:
    def __init__(
        self,
        sessions: SessionFactory,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], UUID] | None = None,
        inference: InferenceEngine | None = None,
    ) -> None:
        self._sessions = sessions
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or uuid4
        self._inference = inference or MockInferenceEngine()

    def create(
        self, snapshot: FeatureSnapshot, event_ids: Sequence[str]
    ) -> tuple[Prediction, AuditRecord]:
        created_at = self._clock()
        if created_at.utcoffset() is None:
            raise ValueError("Prediction clock must return a timezone-aware datetime.")
        prediction_id = f"prediction_{self._id_factory().hex}"
        audit_id = f"audit_{self._id_factory().hex}"
        prediction = Prediction.model_validate(
            self._inference.predict(
                snapshot,
                prediction_id=prediction_id,
                audit_id=audit_id,
                created_at=created_at.isoformat().replace("+00:00", "Z"),
            )
        )
        audit = AuditRecord(
            schema_version="0.1.0",
            twin_id=snapshot.twin_id,
            audit_id=audit_id,
            recorded_at=created_at,
            action="PREDICTION_CREATED",
            actor="oncotwin-backend",
            event_ids=list(event_ids),
            state_version=snapshot.state_version,
            snapshot_id=snapshot.snapshot_id,
            prediction_id=prediction.prediction_id,
            model_version=prediction.model_version,
            data_version=snapshot.data_version,
        )
        with self._sessions() as session:
            session.add(
                PredictionRow(
                    prediction_id=prediction.prediction_id,
                    twin_id=prediction.twin_id,
                    snapshot_id=prediction.snapshot_id,
                    created_at=prediction.created_at,
                    document=prediction.model_dump(mode="json"),
                )
            )
            session.flush()
            session.add(
                AuditRecordRow(
                    audit_id=audit.audit_id,
                    twin_id=audit.twin_id,
                    prediction_id=audit.prediction_id,
                    recorded_at=audit.recorded_at,
                    document=audit.model_dump(mode="json"),
                )
            )
            session.commit()
        return prediction.model_copy(deep=True), audit.model_copy(deep=True)

    def get_prediction(self, prediction_id: str) -> Prediction:
        with self._sessions() as session:
            row = session.get(PredictionRow, prediction_id)
            if row is None:
                raise PredictionNotFoundError(prediction_id)
            return Prediction.model_validate(row.document)

    def get_audit(self, audit_id: str) -> AuditRecord:
        with self._sessions() as session:
            row = session.get(AuditRecordRow, audit_id)
            if row is None:
                raise AuditNotFoundError(audit_id)
            return AuditRecord.model_validate(row.document)

    def list_predictions(
        self, twin_id: str, *, limit: int, offset: int
    ) -> tuple[list[Prediction], int]:
        with self._sessions() as session:
            where = PredictionRow.twin_id == twin_id
            total = session.scalar(
                select(func.count()).select_from(PredictionRow).where(where)
            ) or 0
            rows = session.scalars(
                select(PredictionRow)
                .where(where)
                .order_by(PredictionRow.created_at.desc(), PredictionRow.prediction_id.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            return [Prediction.model_validate(row.document) for row in rows], total

    def list_audits(
        self, twin_id: str, *, limit: int, offset: int
    ) -> tuple[list[AuditRecord], int]:
        with self._sessions() as session:
            where = AuditRecordRow.twin_id == twin_id
            total = session.scalar(
                select(func.count()).select_from(AuditRecordRow).where(where)
            ) or 0
            rows = session.scalars(
                select(AuditRecordRow)
                .where(where)
                .order_by(AuditRecordRow.recorded_at.desc(), AuditRecordRow.audit_id.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            return [AuditRecord.model_validate(row.document) for row in rows], total


def create_database_stores(database_url: str):
    engine = build_engine(database_url)
    sessions = build_session_factory(engine)
    return (
        DatabaseEventStore(sessions),
        DatabaseSnapshotStore(sessions),
        DatabasePredictionAuditStore(sessions),
    )
