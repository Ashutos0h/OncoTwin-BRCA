"""
Canonical Data Schema & Entities for OncoTwin-BRCA.

Defines the core data models for the breast cancer digital-twin data foundation:
- Twin
- PatientProfile
- ClinicalEvent
- Observation
- TumourProfile
- FeatureSnapshot
- Prediction
- ModelVersion
- DataVersion
- AuditLog

Guarantees full compatibility with shared JSON contracts (schema_version 0.1.0)
while providing typed representations for database persistence, FHIR adaptation,
and data engineering pipelines.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StrictBool


NonEmptyString = Annotated[str, Field(strict=True, min_length=1)]
PositiveInteger = Annotated[int, Field(strict=True, ge=1)]
Probability = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]
JsonScalar = int | float | str | bool | None


class CanonicalBase(BaseModel):
    """Base model for all canonical entities."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class Provenance(CanonicalBase):
    """Data provenance tracking source system, record ID, and version."""

    source_system: NonEmptyString
    source_record_id: NonEmptyString
    data_version: NonEmptyString


class Twin(CanonicalBase):
    """Digital twin lifecycle anchor entity."""

    twin_id: NonEmptyString
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state_version: int = Field(default=0, ge=0)
    status: Literal["active", "archived", "suspended"] = "active"


class PatientProfile(CanonicalBase):
    """
    Patient demographics and administrative profile.
    Populated from FHIR Patient resource or clinical registry metadata.
    """

    patient_id: NonEmptyString
    twin_id: NonEmptyString
    mrn: str | None = None
    gender: Literal["female", "male", "other", "unknown"] = "unknown"
    birth_date: str | None = None  # YYYY-MM-DD
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClinicalEvent(CanonicalBase):
    """
    Immutable clinical event representing an observation, diagnosis,
    biomarker result, treatment, or follow-up.
    Strictly conforms to contracts/clinical-event.schema.json v0.1.0.
    """

    schema_version: Literal["0.1.0"] = "0.1.0"
    event_id: NonEmptyString
    twin_id: NonEmptyString
    event_type: Literal[
        "PATHOLOGY_RESULT",
        "DIAGNOSIS",
        "BIOMARKER_RESULT",
        "TREATMENT",
        "FOLLOW_UP",
    ]
    effective_time: datetime
    received_time: datetime
    source: NonEmptyString
    quality_status: Literal["valid", "warning", "invalid"]
    provenance: Provenance
    payload: dict[str, JsonScalar]


class Observation(CanonicalBase):
    """
    Granular observation entity corresponding to a single FHIR Observation
    or discrete clinical measurement.
    """

    observation_id: NonEmptyString
    twin_id: NonEmptyString
    code: NonEmptyString
    code_system: str = "http://loinc.org"
    display: str | None = None
    category: Literal["pathology", "biomarker", "vital-signs", "laboratory", "imaging"] = "pathology"
    value_numeric: float | None = None
    value_string: str | None = None
    unit: str | None = None
    status: Literal["preliminary", "final", "amended", "corrected"] = "final"
    effective_time: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TumourProfile(CanonicalBase):
    """
    Standardized tumour profile capturing the 8 primary features
    defined in the project data dictionary.
    """

    profile_id: NonEmptyString
    twin_id: NonEmptyString
    tumour_size_mm: float | None = Field(default=None, ge=0.0)
    grade: int | None = Field(default=None, ge=1, le=4)
    positive_nodes: int | None = Field(default=None, ge=0)
    her2_status: Literal["positive", "negative", "equivocal"] | None = None
    er_status: Literal["positive", "negative"] | None = None
    pr_status: Literal["positive", "negative"] | None = None
    ki67_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    morphology_code: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    missingness_mask: dict[str, int] = Field(default_factory=dict)


class FeatureSnapshot(CanonicalBase):
    """
    Point-in-time feature snapshot derived from twin state.
    Conforms to contracts/feature-snapshot.schema.json v0.1.0.
    """

    schema_version: Literal["0.1.0"] = "0.1.0"
    twin_id: NonEmptyString
    snapshot_id: NonEmptyString
    state_version: PositiveInteger
    created_at: datetime
    data_version: NonEmptyString
    feature_set_version: NonEmptyString
    features: dict[str, JsonScalar]
    missing_fields: list[NonEmptyString]


class ShapValue(CanonicalBase):
    feature: NonEmptyString
    value: float


class Prediction(CanonicalBase):
    """
    Model risk prediction linked to snapshot, audit, and model versions.
    Conforms to contracts/prediction.schema.json v0.1.0.
    """

    schema_version: Literal["0.1.0"] = "0.1.0"
    twin_id: NonEmptyString
    prediction_id: NonEmptyString
    snapshot_id: NonEmptyString
    state_version: PositiveInteger
    data_version: NonEmptyString
    audit_id: NonEmptyString
    created_at: datetime
    model_name: NonEmptyString
    model_version: NonEmptyString
    is_mock: StrictBool
    risk_probability: Probability
    horizon_months: PositiveInteger
    confidence: Literal["not_assessed", "low", "moderate", "high"]
    ood_flag: StrictBool | None = None
    shap_values: list[ShapValue] = Field(default_factory=list)
    warnings: list[NonEmptyString] = Field(default_factory=list)


class ModelVersion(CanonicalBase):
    """
    Metadata for a registered AI/ML prediction model.
    """

    model_id: NonEmptyString
    name: NonEmptyString
    version: NonEmptyString
    algorithm: NonEmptyString  # e.g., "XGBClassifier", "LogisticRegression"
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    data_version: NonEmptyString
    artifact_path: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    active: StrictBool = True


class DataVersion(CanonicalBase):
    """
    Provenance record for a cohort dataset version, fingerprinting raw and
    processed data assets with SHA-256 hashes.
    """

    data_version_id: NonEmptyString
    name: NonEmptyString
    dataset_name: Literal["METABRIC", "TCGA-BRCA", "Synthea", "Synthetic"]
    record_count: int = Field(ge=0)
    content_sha256: NonEmptyString
    schema_version: NonEmptyString = "0.1.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLog(CanonicalBase):
    """
    Tamper-evident audit log capturing every event acceptance, state rebuild,
    and prediction generation with full lineage.
    Conforms to contracts/audit-record.schema.json v0.1.0.
    """

    schema_version: Literal["0.1.0"] = "0.1.0"
    twin_id: NonEmptyString
    audit_id: NonEmptyString
    recorded_at: datetime
    action: Literal["EVENT_ACCEPTED", "STATE_REBUILT", "PREDICTION_CREATED"]
    actor: NonEmptyString
    event_ids: list[NonEmptyString]
    state_version: PositiveInteger
    snapshot_id: NonEmptyString
    prediction_id: NonEmptyString
    model_version: NonEmptyString
    data_version: NonEmptyString
