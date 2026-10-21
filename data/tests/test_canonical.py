"""
Unit tests for data.src.canonical — Pydantic models for the 10 canonical entities.
"""
from datetime import datetime, timezone
import pytest

from data.src.canonical import (
    AuditLog,
    ClinicalEvent,
    DataVersion,
    FeatureSnapshot,
    ModelVersion,
    Observation,
    PatientProfile,
    Prediction,
    Provenance,
    TumourProfile,
    Twin,
)


class TestCanonicalEntities:

    def test_clinical_event_required_fields(self):
        now = datetime.now(timezone.utc)
        event = ClinicalEvent(
            schema_version="0.1.0",
            event_id="evt_test_01",
            twin_id="TWIN_01",
            event_type="PATHOLOGY_RESULT",
            effective_time=now,
            received_time=now,
            source="test_runner",
            quality_status="valid",
            provenance=Provenance(
                source_system="synthetic",
                source_record_id="rec_01",
                data_version="1.0.0",
            ),
            payload={"tumour_size_mm": 25.0, "grade": 2},
        )
        assert event.event_id == "evt_test_01"
        assert event.event_type == "PATHOLOGY_RESULT"
        assert event.quality_status == "valid"
        assert event.payload["tumour_size_mm"] == 25.0

    def test_twin_entity(self):
        twin = Twin(twin_id="TWIN_001", state_version=0, status="active")
        assert twin.twin_id == "TWIN_001"
        assert twin.state_version == 0
        assert twin.status == "active"

    def test_patient_profile(self):
        profile = PatientProfile(
            patient_id="pat_100",
            twin_id="TWIN_100",
            mrn="MRN-100",
            gender="female",
            birth_date="1980-01-01",
        )
        assert profile.gender == "female"
        assert profile.mrn == "MRN-100"

    def test_observation_entity(self):
        obs = Observation(
            observation_id="obs_100",
            twin_id="TWIN_100",
            code="21889-1",
            display="Tumor size",
            effective_time=datetime.now(timezone.utc),
            value_numeric=22.0,
            unit="mm",
        )
        assert obs.value_numeric == 22.0
        assert obs.unit == "mm"

    def test_tumour_profile(self):
        tumour = TumourProfile(
            profile_id="tum_100",
            twin_id="TWIN_100",
            tumour_size_mm=30.0,
            grade=3,
            positive_nodes=2,
            her2_status="positive",
            er_status="negative",
            pr_status="negative",
            ki67_percent=45.0,
        )
        assert tumour.tumour_size_mm == 30.0
        assert tumour.grade == 3
        assert tumour.her2_status == "positive"

    def test_model_version(self):
        model = ModelVersion(
            model_id="mod_001",
            name="XGBoost_BRCA",
            version="1.0.0",
            algorithm="XGBClassifier",
            data_version="metabric-v1.0.0",
            metrics={"auroc": 0.732, "brier": 0.178},
        )
        assert model.name == "XGBoost_BRCA"
        assert model.metrics["auroc"] == 0.732

    def test_data_version(self):
        dv = DataVersion(
            data_version_id="dv_001",
            name="METABRIC 5-Year",
            dataset_name="METABRIC",
            record_count=1944,
            content_sha256="abc123456789",
        )
        assert dv.record_count == 1944
        assert dv.dataset_name == "METABRIC"

    def test_audit_log(self):
        now = datetime.now(timezone.utc)
        audit = AuditLog(
            schema_version="0.1.0",
            twin_id="TWIN_01",
            audit_id="aud_01",
            recorded_at=now,
            action="PREDICTION_CREATED",
            actor="inference_service",
            event_ids=["evt_01", "evt_02"],
            state_version=1,
            snapshot_id="snap_01",
            prediction_id="pred_01",
            model_version="1.0.0",
            data_version="metabric-v1.0.0",
        )
        assert audit.action == "PREDICTION_CREATED"
        assert audit.state_version == 1
