"""SQLAlchemy persistence for twins, events, snapshots, predictions, and audits."""

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    create_engine,
    event,
    func,
    select,
)
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


class PatientProfileRow(Base):
    __tablename__ = "patient_profiles"
    patient_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    twin_id: Mapped[str] = mapped_column(
        ForeignKey("twins.twin_id"), nullable=False, unique=True
    )
    gender: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    birth_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mrn: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    __table_args__ = (Index("ix_patient_profiles_twin_id", "twin_id"),)


class ObservationRow(Base):
    __tablename__ = "observations"
    observation_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    twin_id: Mapped[str] = mapped_column(ForeignKey("twins.twin_id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="pathology")
    effective_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="final")
    document: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    __table_args__ = (
        Index("ix_observations_twin_id", "twin_id"),
        Index("ix_observations_code", "code"),
        Index("ix_observations_effective_time", "effective_time"),
    )


class TumourProfileRow(Base):
    __tablename__ = "tumour_profiles"
    profile_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    twin_id: Mapped[str] = mapped_column(
        ForeignKey("twins.twin_id"), nullable=False, unique=True
    )
    tumour_size_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    positive_nodes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    her2_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    er_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pr_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    __table_args__ = (Index("ix_tumour_profiles_twin_id", "twin_id"),)


class ModelVersionRow(Base):
    __tablename__ = "model_versions"
    model_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    document: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    __table_args__ = (Index("ix_model_versions_name_version", "name", "version"),)


class DataVersionRow(Base):
    __tablename__ = "data_versions"
    data_version_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    dataset_name: Mapped[str] = mapped_column(String(128), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, nullable=False)
    __table_args__ = (Index("ix_data_versions_content_sha256", "content_sha256"),)



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


class DatabaseDataFoundation:
    """
    Manages canonical entities (PatientProfile, Observation, TumourProfile,
    ModelVersion, DataVersion) and advanced audit/lineage queries.
    """

    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    def save_patient_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        with self._sessions() as session:
            pid = str(profile["patient_id"])
            twin_id = str(profile["twin_id"])
            existing = session.get(PatientProfileRow, pid)
            if existing:
                existing.gender = profile.get("gender", "unknown")
                existing.birth_date = profile.get("birth_date")
                existing.mrn = profile.get("mrn")
                existing.document = profile
            else:
                row = PatientProfileRow(
                    patient_id=pid,
                    twin_id=twin_id,
                    gender=profile.get("gender", "unknown"),
                    birth_date=profile.get("birth_date"),
                    mrn=profile.get("mrn"),
                    created_at=datetime.now(timezone.utc),
                    document=profile,
                )
                session.add(row)
            session.commit()
            return profile

    def get_patient_profile(self, twin_id: str) -> dict[str, Any] | None:
        with self._sessions() as session:
            row = session.scalar(
                select(PatientProfileRow).where(PatientProfileRow.twin_id == twin_id)
            )
            return dict(row.document) if row else None

    def save_tumour_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        with self._sessions() as session:
            prof_id = str(profile["profile_id"])
            twin_id = str(profile["twin_id"])
            existing = session.get(TumourProfileRow, prof_id)
            if existing:
                existing.tumour_size_mm = profile.get("tumour_size_mm")
                existing.grade = profile.get("grade")
                existing.positive_nodes = profile.get("positive_nodes")
                existing.her2_status = profile.get("her2_status")
                existing.er_status = profile.get("er_status")
                existing.pr_status = profile.get("pr_status")
                existing.updated_at = datetime.now(timezone.utc)
                existing.document = profile
            else:
                row = TumourProfileRow(
                    profile_id=prof_id,
                    twin_id=twin_id,
                    tumour_size_mm=profile.get("tumour_size_mm"),
                    grade=profile.get("grade"),
                    positive_nodes=profile.get("positive_nodes"),
                    her2_status=profile.get("her2_status"),
                    er_status=profile.get("er_status"),
                    pr_status=profile.get("pr_status"),
                    updated_at=datetime.now(timezone.utc),
                    document=profile,
                )
                session.add(row)
            session.commit()
            return profile

    def get_tumour_profile(self, twin_id: str) -> dict[str, Any] | None:
        with self._sessions() as session:
            row = session.scalar(
                select(TumourProfileRow).where(TumourProfileRow.twin_id == twin_id)
            )
            return dict(row.document) if row else None

    def save_observation(self, obs: dict[str, Any]) -> dict[str, Any]:
        with self._sessions() as session:
            obs_id = str(obs["observation_id"])
            eff_str = obs.get("effective_time")
            try:
                eff_dt = datetime.fromisoformat(str(eff_str).replace("Z", "+00:00"))
            except Exception:
                eff_dt = datetime.now(timezone.utc)

            row = ObservationRow(
                observation_id=obs_id,
                twin_id=str(obs["twin_id"]),
                code=str(obs["code"]),
                category=str(obs.get("category", "pathology")),
                effective_time=eff_dt,
                status=str(obs.get("status", "final")),
                document=obs,
            )
            session.add(row)
            session.commit()
            return obs

    def list_observations(self, twin_id: str) -> list[dict[str, Any]]:
        with self._sessions() as session:
            rows = session.scalars(
                select(ObservationRow)
                .where(ObservationRow.twin_id == twin_id)
                .order_by(ObservationRow.effective_time.asc())
            ).all()
            return [dict(r.document) for r in rows]

    def register_model_version(self, model_data: dict[str, Any]) -> dict[str, Any]:
        with self._sessions() as session:
            mid = str(model_data["model_id"])
            row = ModelVersionRow(
                model_id=mid,
                name=str(model_data["name"]),
                version=str(model_data["version"]),
                algorithm=str(model_data["algorithm"]),
                created_at=datetime.now(timezone.utc),
                active=bool(model_data.get("active", True)),
                document=model_data,
            )
            session.add(row)
            session.commit()
            return model_data

    def get_model_version(self, name: str, version: str) -> dict[str, Any] | None:
        with self._sessions() as session:
            row = session.scalar(
                select(ModelVersionRow).where(
                    ModelVersionRow.name == name, ModelVersionRow.version == version
                )
            )
            return dict(row.document) if row else None

    def register_data_version(self, version_data: dict[str, Any]) -> dict[str, Any]:
        with self._sessions() as session:
            dvid = str(version_data["data_version_id"])
            row = DataVersionRow(
                data_version_id=dvid,
                name=str(version_data["name"]),
                dataset_name=str(version_data.get("dataset_name", "METABRIC")),
                record_count=int(version_data.get("record_count", 0)),
                content_sha256=str(version_data["content_sha256"]),
                created_at=datetime.now(timezone.utc),
                document=version_data,
            )
            session.add(row)
            session.commit()
            return version_data

    def get_data_version(self, data_version_id: str) -> dict[str, Any] | None:
        with self._sessions() as session:
            row = session.get(DataVersionRow, data_version_id)
            return dict(row.document) if row else None

    def get_prediction_lineage(self, prediction_id: str) -> dict[str, Any] | None:
        """
        Retrieves the complete provenance lineage for a prediction:
        Prediction -> Snapshot -> Twin State -> Audit Record -> Input Events.
        """
        with self._sessions() as session:
            pred_row = session.get(PredictionRow, prediction_id)
            if not pred_row:
                return None

            pred_doc = dict(pred_row.document)
            snap_id = pred_row.snapshot_id
            snap_row = session.get(FeatureSnapshotRow, snap_id)
            snap_doc = dict(snap_row.document) if snap_row else None

            audit_row = session.scalar(
                select(AuditRecordRow).where(AuditRecordRow.prediction_id == prediction_id)
            )
            audit_doc = dict(audit_row.document) if audit_row else None

            # Retrieve input clinical events referenced by snapshot
            event_ids = snap_row.event_ids if snap_row else []
            events = []
            if event_ids:
                event_rows = session.scalars(
                    select(ClinicalEventRow).where(ClinicalEventRow.event_id.in_(event_ids))
                ).all()
                events = [dict(e.document) for e in event_rows]

            return {
                "prediction": pred_doc,
                "snapshot": snap_doc,
                "audit": audit_doc,
                "referenced_events": events,
                "state_version": pred_doc.get("state_version"),
                "model_version": pred_doc.get("model_version"),
                "data_version": pred_doc.get("data_version"),
            }


def create_database_stores(database_url: str, *, inference: InferenceEngine | None = None):
    engine = build_engine(database_url)
    sessions = build_session_factory(engine)
    return (
        DatabaseEventStore(sessions),
        DatabaseSnapshotStore(sessions),
        DatabasePredictionAuditStore(sessions, inference=inference),
    )


def create_data_foundation(database_url: str) -> DatabaseDataFoundation:
    engine = build_engine(database_url)
    sessions = build_session_factory(engine)
    return DatabaseDataFoundation(sessions)

