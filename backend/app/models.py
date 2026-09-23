"""Pydantic representations of the shared JSON contracts and API-only models."""

from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictBool


NonEmptyString = Annotated[str, Field(strict=True, min_length=1)]
JsonString = Annotated[str, Field(strict=True)]
PositiveInteger = Annotated[int, Field(strict=True, ge=1)]
Probability = Annotated[float, Field(strict=True, ge=0, le=1)]
JsonScalar = Annotated[int, Field(strict=True)] | Annotated[float, Field(strict=True)] | JsonString | StrictBool | None


def _unique(items: list[str]) -> list[str]:
    if len(items) != len(set(items)):
        raise ValueError("Items must be unique.")
    return items


UniqueStrings = Annotated[list[NonEmptyString], AfterValidator(_unique)]


class ContractModel(BaseModel):
    """Base configuration shared by contract models."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Provenance(ContractModel):
    source_system: NonEmptyString
    source_record_id: NonEmptyString
    data_version: NonEmptyString


class ClinicalEvent(ContractModel):
    schema_version: Literal["0.1.0"]
    twin_id: NonEmptyString
    event_id: NonEmptyString
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
    payload: Annotated[dict[str, JsonScalar], Field(min_length=1)]


class TwinState(ContractModel):
    schema_version: Literal["0.1.0"]
    twin_id: NonEmptyString
    state_version: PositiveInteger
    as_of: datetime
    event_ids: UniqueStrings
    data_version: NonEmptyString
    values: Annotated[dict[str, JsonScalar], Field(min_length=1)]
    missing_fields: UniqueStrings
    quality_warnings: UniqueStrings


class FeatureSnapshot(ContractModel):
    schema_version: Literal["0.1.0"]
    twin_id: NonEmptyString
    snapshot_id: NonEmptyString
    state_version: PositiveInteger
    created_at: datetime
    data_version: NonEmptyString
    feature_set_version: NonEmptyString
    features: Annotated[dict[str, JsonScalar], Field(min_length=1)]
    missing_fields: UniqueStrings


class ShapValue(ContractModel):
    feature: NonEmptyString
    value: Annotated[float, Field(strict=True)]


class Prediction(ContractModel):
    schema_version: Literal["0.1.0"]
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
    ood_flag: StrictBool | None
    shap_values: list[ShapValue]
    warnings: UniqueStrings


class AuditRecord(ContractModel):
    schema_version: Literal["0.1.0"]
    twin_id: NonEmptyString
    audit_id: NonEmptyString
    recorded_at: datetime
    action: Literal["EVENT_ACCEPTED", "STATE_REBUILT", "PREDICTION_CREATED"]
    actor: NonEmptyString
    event_ids: UniqueStrings
    state_version: PositiveInteger
    snapshot_id: NonEmptyString
    prediction_id: NonEmptyString
    model_version: NonEmptyString
    data_version: NonEmptyString


class TwinCreate(BaseModel):
    """API command; not part of the shared cross-module contracts."""

    model_config = ConfigDict(extra="forbid")
    twin_id: NonEmptyString


class TwinCreated(BaseModel):
    twin_id: NonEmptyString
    status: Literal["created"] = "created"


class TwinSummary(BaseModel):
    """API-only twin listing item."""

    twin_id: NonEmptyString
    state_version: Annotated[int, Field(strict=True, ge=0)]


class EventAccepted(BaseModel):
    twin_id: NonEmptyString
    event_id: NonEmptyString
    status: Literal["accepted"] = "accepted"
    state_version: PositiveInteger


class ErrorResponse(BaseModel):
    detail: str


PageItem = TypeVar("PageItem")


class Page(BaseModel, Generic[PageItem]):
    """API-only offset page; items remain shared contract objects."""

    items: list[PageItem]
    total: Annotated[int, Field(ge=0)]
    limit: Annotated[int, Field(ge=1, le=200)]
    offset: Annotated[int, Field(ge=0)]
