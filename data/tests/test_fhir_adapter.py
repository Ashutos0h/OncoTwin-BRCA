"""
Tests for data.src.fhir_adapter — FHIR R4 Observation → ClinicalEvent mapping.

Covers:
  - All supported LOINC codes (tumour size, grade, nodes, HER2, ER, PR, Ki-67, diagnosis)
  - Unit conversion (cm → mm)
  - Grade 1–4 support (Nottingham 1–3 + Grade 4 undifferentiated)
  - Compound / multi-measurement observations via component[] (panels)
  - IHC qualitative text, ordinal scores ('0', '1+', '2+', '3+'), and quantitative values
  - Missingness tracking (null values → quality_status='warning')
  - Rejection of unsupported codes, invalid statuses, impossible values, bad units
  - Provenance field population
  - bundle_to_events: happy path, skip log for unsupported entries
  - Schema conformance for every mapping (validate_event)
"""
import pytest
from data.src.fhir_adapter import observation_to_event, bundle_to_events, FEATURE_DICT
from data.src.validation import validate_event


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_obs():
    """Minimal valid FHIR Observation skeleton (tumour size)."""
    return {
        "resourceType": "Observation",
        "id": "obs-123",
        "status": "final",
        "code": {
            "coding": [{"system": "http://loinc.org", "code": "21889-1", "display": "Size Tumor"}]
        },
        "subject": {"reference": "Patient/SYNTHETIC_TWIN_001"},
        "effectiveDateTime": "2026-09-01T10:00:00Z",
        "valueQuantity": {"value": 31.0, "unit": "mm"},
        "meta": {"versionId": "1", "lastUpdated": "2026-09-01T10:00:00Z"},
    }


def _obs(code: str, vq: dict | None = None, vcc: dict | None = None, vs: str | None = None) -> dict:
    """Build a minimal valid Observation for a given LOINC code."""
    obs = {
        "resourceType": "Observation",
        "id": f"obs-{code}",
        "status": "final",
        "code": {"coding": [{"system": "http://loinc.org", "code": code}]},
        "subject": {"reference": "Patient/SYNTHETIC_TWIN_001"},
        "effectiveDateTime": "2026-09-01T10:00:00Z",
        "meta": {"versionId": "1", "lastUpdated": "2026-09-01T10:00:00Z"},
    }
    if vq is not None:
        obs["valueQuantity"] = vq
    if vcc is not None:
        obs["valueCodeableConcept"] = vcc
    if vs is not None:
        obs["valueString"] = vs
    return obs


TWIN = "SYNTHETIC_TWIN_001"


# ---------------------------------------------------------------------------
# PATHOLOGY_RESULT — Tumour size
# ---------------------------------------------------------------------------

class TestTumourSize:

    def test_valid_mm(self, base_obs):
        event = observation_to_event(base_obs, TWIN)
        validate_event(event)
        assert event["payload"]["tumour_size_mm"] == 31.0
        assert event["event_type"] == "PATHOLOGY_RESULT"
        assert event["quality_status"] == "valid"

    def test_valid_cm_conversion(self, base_obs):
        base_obs["valueQuantity"] = {"value": 3.1, "unit": "cm"}
        event = observation_to_event(base_obs, TWIN)
        assert event["payload"]["tumour_size_mm"] == pytest.approx(31.0)

    def test_zero_size_allowed(self, base_obs):
        base_obs["valueQuantity"]["value"] = 0.0
        event = observation_to_event(base_obs, TWIN)
        assert event["payload"]["tumour_size_mm"] == 0.0

    def test_invalid_unit(self, base_obs):
        base_obs["valueQuantity"]["unit"] = "inch"
        with pytest.raises(ValueError, match="Unsupported unit"):
            observation_to_event(base_obs, TWIN)

    def test_negative_value_rejected(self, base_obs):
        base_obs["valueQuantity"]["value"] = -5.0
        with pytest.raises(ValueError, match="Impossible or missing value"):
            observation_to_event(base_obs, TWIN)

    def test_missing_value_null(self, base_obs):
        base_obs["valueQuantity"] = {}
        event = observation_to_event(base_obs, TWIN)
        assert event["payload"]["tumour_size_mm"] is None
        assert event["quality_status"] == "warning"

    def test_schema_conforms(self, base_obs):
        validate_event(observation_to_event(base_obs, TWIN))


# ---------------------------------------------------------------------------
# PATHOLOGY_RESULT — Histologic grade
# ---------------------------------------------------------------------------

class TestHistologicGrade:

    def test_valid_grade_1(self):
        obs = _obs("33732-9", vq={"value": 1})
        event = observation_to_event(obs, TWIN)
        validate_event(event)
        assert event["payload"]["grade"] == 1
        assert event["event_type"] == "PATHOLOGY_RESULT"
        assert event["quality_status"] == "valid"

    def test_valid_grade_3(self):
        obs = _obs("33732-9", vq={"value": 3})
        assert observation_to_event(obs, TWIN)["payload"]["grade"] == 3

    def test_valid_grade_4(self):
        obs = _obs("33732-9", vq={"value": 4})
        event = observation_to_event(obs, TWIN)
        validate_event(event)
        assert event["payload"]["grade"] == 4
        assert event["quality_status"] == "valid"

    def test_grade_5_rejected(self):
        obs = _obs("33732-9", vq={"value": 5})
        with pytest.raises(ValueError, match="Grade must be between 1 and 4"):
            observation_to_event(obs, TWIN)

    def test_grade_0_rejected(self):
        obs = _obs("33732-9", vq={"value": 0})
        with pytest.raises(ValueError, match="Grade must be between 1 and 4"):
            observation_to_event(obs, TWIN)

    def test_missing_grade_null(self):
        obs = _obs("33732-9", vq={})
        event = observation_to_event(obs, TWIN)
        assert event["payload"]["grade"] is None
        assert event["quality_status"] == "warning"


# ---------------------------------------------------------------------------
# PATHOLOGY_RESULT — Positive lymph nodes
# ---------------------------------------------------------------------------

class TestPositiveNodes:

    def test_valid_node_count(self):
        obs = _obs("21893-3", vq={"value": 3})
        event = observation_to_event(obs, TWIN)
        validate_event(event)
        assert event["payload"]["positive_nodes"] == 3

    def test_zero_nodes_allowed(self):
        obs = _obs("21893-3", vq={"value": 0})
        assert observation_to_event(obs, TWIN)["payload"]["positive_nodes"] == 0

    def test_negative_nodes_rejected(self):
        obs = _obs("21893-3", vq={"value": -1})
        with pytest.raises(ValueError, match="Nodes cannot be negative"):
            observation_to_event(obs, TWIN)

    def test_missing_nodes_null(self):
        obs = _obs("21893-3", vq={})
        event = observation_to_event(obs, TWIN)
        assert event["payload"]["positive_nodes"] is None
        assert event["quality_status"] == "warning"


# ---------------------------------------------------------------------------
# BIOMARKER_RESULT — HER2 (Qualitative, Ordinal, Quantitative)
# ---------------------------------------------------------------------------

class TestHER2:

    def _her2_obs(self, text: str | None):
        vcc = {"text": text} if text is not None else {}
        return _obs("85319-2", vcc=vcc)

    def test_her2_positive(self):
        event = observation_to_event(self._her2_obs("positive"), TWIN)
        validate_event(event)
        assert event["payload"]["her2_status"] == "positive"
        assert event["event_type"] == "BIOMARKER_RESULT"
        assert event["quality_status"] == "valid"

    def test_her2_negative(self):
        assert observation_to_event(self._her2_obs("negative"), TWIN)["payload"]["her2_status"] == "negative"

    def test_her2_equivocal(self):
        assert observation_to_event(self._her2_obs("equivocal"), TWIN)["payload"]["her2_status"] == "equivocal"

    def test_her2_case_insensitive(self):
        vcc = {"text": "Positive"}
        obs = _obs("85319-2", vcc=vcc)
        assert observation_to_event(obs, TWIN)["payload"]["her2_status"] == "positive"

    def test_her2_ordinal_scores(self):
        # 0 -> negative
        obs0 = _obs("85319-2", vs="0")
        assert observation_to_event(obs0, TWIN)["payload"]["her2_status"] == "negative"

        # 1+ -> negative
        obs1 = _obs("85319-2", vs="1+")
        assert observation_to_event(obs1, TWIN)["payload"]["her2_status"] == "negative"

        # 2+ -> equivocal
        obs2 = _obs("85319-2", vs="2+")
        assert observation_to_event(obs2, TWIN)["payload"]["her2_status"] == "equivocal"

        # 3+ -> positive
        obs3 = _obs("85319-2", vs="3+")
        assert observation_to_event(obs3, TWIN)["payload"]["her2_status"] == "positive"

    def test_her2_numeric_quantity(self):
        # Score 0 -> negative
        obs0 = _obs("85319-2", vq={"value": 0})
        assert observation_to_event(obs0, TWIN)["payload"]["her2_status"] == "negative"

        # Score 2 -> equivocal
        obs2 = _obs("85319-2", vq={"value": 2})
        assert observation_to_event(obs2, TWIN)["payload"]["her2_status"] == "equivocal"

        # Score 3 -> positive
        obs3 = _obs("85319-2", vq={"value": 3})
        assert observation_to_event(obs3, TWIN)["payload"]["her2_status"] == "positive"

        # Score 4 -> invalid
        obs4 = _obs("85319-2", vq={"value": 4})
        with pytest.raises(ValueError, match="Numeric HER2 score"):
            observation_to_event(obs4, TWIN)

    def test_her2_invalid_text(self):
        with pytest.raises(ValueError, match="Unsupported IHC value"):
            observation_to_event(self._her2_obs("inconclusive_xyz"), TWIN)

    def test_her2_from_coding_display(self):
        vcc = {"coding": [{"display": "Negative"}]}
        obs = _obs("85319-2", vcc=vcc)
        assert observation_to_event(obs, TWIN)["payload"]["her2_status"] == "negative"

    def test_her2_missing_null(self):
        obs = _obs("85319-2", vcc={})
        event = observation_to_event(obs, TWIN)
        assert event["payload"]["her2_status"] is None
        assert event["quality_status"] == "warning"


# ---------------------------------------------------------------------------
# BIOMARKER_RESULT — ER / PR
# ---------------------------------------------------------------------------

class TestERPR:

    def test_er_positive(self):
        obs = _obs("85337-4", vcc={"text": "positive"})
        event = observation_to_event(obs, TWIN)
        validate_event(event)
        assert event["payload"]["er_status"] == "positive"
        assert event["event_type"] == "BIOMARKER_RESULT"

    def test_er_abbreviation(self):
        obs = _obs("85337-4", vs="POS")
        assert observation_to_event(obs, TWIN)["payload"]["er_status"] == "positive"

    def test_pr_negative(self):
        obs = _obs("85347-3", vcc={"text": "negative"})
        event = observation_to_event(obs, TWIN)
        validate_event(event)
        assert event["payload"]["pr_status"] == "negative"

    def test_er_percentage_positive(self):
        obs = _obs("85337-4", vq={"value": 75.0, "unit": "%"})
        assert observation_to_event(obs, TWIN)["payload"]["er_status"] == "positive"

    def test_pr_percentage_negative(self):
        obs = _obs("85347-3", vq={"value": 0.0, "unit": "%"})
        assert observation_to_event(obs, TWIN)["payload"]["pr_status"] == "negative"


# ---------------------------------------------------------------------------
# BIOMARKER_RESULT — Ki-67
# ---------------------------------------------------------------------------

class TestKi67:

    def test_valid_ki67(self):
        obs = _obs("59847-4", vq={"value": 25.0, "unit": "%"})
        event = observation_to_event(obs, TWIN)
        validate_event(event)
        assert event["payload"]["ki67_percent"] == 25.0
        assert event["event_type"] == "BIOMARKER_RESULT"

    def test_ki67_zero_allowed(self):
        obs = _obs("59847-4", vq={"value": 0.0, "unit": "%"})
        assert observation_to_event(obs, TWIN)["payload"]["ki67_percent"] == 0.0

    def test_ki67_100_allowed(self):
        obs = _obs("59847-4", vq={"value": 100.0, "unit": "%"})
        assert observation_to_event(obs, TWIN)["payload"]["ki67_percent"] == 100.0

    def test_ki67_over_100_rejected(self):
        obs = _obs("59847-4", vq={"value": 101.0, "unit": "%"})
        with pytest.raises(ValueError, match="Impossible Ki-67"):
            observation_to_event(obs, TWIN)

    def test_ki67_negative_rejected(self):
        obs = _obs("59847-4", vq={"value": -1.0, "unit": "%"})
        with pytest.raises(ValueError, match="Impossible Ki-67"):
            observation_to_event(obs, TWIN)

    def test_ki67_wrong_unit(self):
        obs = _obs("59847-4", vq={"value": 25.0, "unit": "fraction"})
        with pytest.raises(ValueError, match="Unsupported unit"):
            observation_to_event(obs, TWIN)

    def test_ki67_missing_null(self):
        obs = _obs("59847-4", vq={})
        event = observation_to_event(obs, TWIN)
        assert event["payload"]["ki67_percent"] is None
        assert event["quality_status"] == "warning"


# ---------------------------------------------------------------------------
# DIAGNOSIS — morphology code
# ---------------------------------------------------------------------------

class TestDiagnosis:

    def test_valid_morphology(self):
        vcc = {"coding": [{"system": "http://snomed.info/sct", "code": "8500/3"}], "text": "IDC"}
        obs = _obs("29308-4", vcc=vcc)
        event = observation_to_event(obs, TWIN)
        validate_event(event)
        assert event["payload"]["morphology_code"] == "8500/3"
        assert event["event_type"] == "DIAGNOSIS"

    def test_missing_morphology_null(self):
        obs = _obs("29308-4", vcc={})
        event = observation_to_event(obs, TWIN)
        assert event["payload"]["morphology_code"] is None
        assert event["quality_status"] == "warning"


# ---------------------------------------------------------------------------
# Compound Observations via component[] (Panels)
# ---------------------------------------------------------------------------

class TestCompoundObservations:

    def test_biomarker_panel_components(self):
        panel = {
            "resourceType": "Observation",
            "id": "panel-bio-01",
            "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": "85319-2"}]},
            "subject": {"reference": "Patient/SYNTHETIC_TWIN_001"},
            "effectiveDateTime": "2026-09-01T10:00:00Z",
            "component": [
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "85319-2"}]},
                    "valueString": "3+",
                },
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "85337-4"}]},
                    "valueQuantity": {"value": 85.0, "unit": "%"},
                },
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "85347-3"}]},
                    "valueQuantity": {"value": 0.0, "unit": "%"},
                },
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "59847-4"}]},
                    "valueQuantity": {"value": 28.0, "unit": "%"},
                },
            ],
            "meta": {"versionId": "1", "lastUpdated": "2026-09-01T10:00:00Z"},
        }
        event = observation_to_event(panel, TWIN)
        validate_event(event)
        assert event["event_type"] == "BIOMARKER_RESULT"
        assert event["payload"]["her2_status"] == "positive"
        assert event["payload"]["er_status"] == "positive"
        assert event["payload"]["pr_status"] == "negative"
        assert event["payload"]["ki67_percent"] == 28.0
        assert event["quality_status"] == "valid"

    def test_pathology_panel_components(self):
        panel = {
            "resourceType": "Observation",
            "id": "panel-path-01",
            "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": "21889-1"}]},
            "subject": {"reference": "Patient/SYNTHETIC_TWIN_001"},
            "effectiveDateTime": "2026-09-01T10:00:00Z",
            "component": [
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "21889-1"}]},
                    "valueQuantity": {"value": 24.5, "unit": "mm"},
                },
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "33732-9"}]},
                    "valueQuantity": {"value": 3},
                },
                {
                    "code": {"coding": [{"system": "http://loinc.org", "code": "21893-3"}]},
                    "valueQuantity": {"value": 2},
                },
            ],
            "meta": {"versionId": "1", "lastUpdated": "2026-09-01T10:00:00Z"},
        }
        event = observation_to_event(panel, TWIN)
        validate_event(event)
        assert event["event_type"] == "PATHOLOGY_RESULT"
        assert event["payload"]["tumour_size_mm"] == 24.5
        assert event["payload"]["grade"] == 3
        assert event["payload"]["positive_nodes"] == 2
        assert event["quality_status"] == "valid"


# ---------------------------------------------------------------------------
# Cross-cutting: unsupported code / invalid status / missing twin_id
# ---------------------------------------------------------------------------

class TestRejections:

    def test_unsupported_code(self, base_obs):
        base_obs["code"]["coding"][0]["code"] = "99999-9"
        with pytest.raises(ValueError, match="Unsupported observation code"):
            observation_to_event(base_obs, TWIN)

    def test_wrong_resource_type(self, base_obs):
        base_obs["resourceType"] = "Condition"
        with pytest.raises(ValueError, match="Expected resourceType"):
            observation_to_event(base_obs, TWIN)

    def test_preliminary_status_rejected(self, base_obs):
        base_obs["status"] = "preliminary"
        with pytest.raises(ValueError, match="Invalid Observation status"):
            observation_to_event(base_obs, TWIN)

    def test_amended_status_accepted(self, base_obs):
        base_obs["status"] = "amended"
        event = observation_to_event(base_obs, TWIN)
        assert event["schema_version"] == "0.1.0"

    def test_corrected_status_accepted(self, base_obs):
        base_obs["status"] = "corrected"
        assert observation_to_event(base_obs, TWIN)

    def test_empty_twin_id_rejected(self, base_obs):
        with pytest.raises(ValueError, match="twin_id"):
            observation_to_event(base_obs, "")

    def test_missing_effective_time_rejected(self, base_obs):
        del base_obs["effectiveDateTime"]
        with pytest.raises(ValueError, match="Missing effectiveDateTime"):
            observation_to_event(base_obs, TWIN)

    def test_effective_period_used_as_fallback(self, base_obs):
        del base_obs["effectiveDateTime"]
        base_obs["effectivePeriod"] = {"start": "2026-09-01T10:00:00Z"}
        event = observation_to_event(base_obs, TWIN)
        assert event["effective_time"] == "2026-09-01T10:00:00Z"


# ---------------------------------------------------------------------------
# Provenance fields
# ---------------------------------------------------------------------------

class TestProvenance:

    def test_provenance_fields_populated(self, base_obs):
        event = observation_to_event(base_obs, TWIN)
        prov = event["provenance"]
        assert prov["source_system"] == "fhir"
        assert prov["source_record_id"] == "obs-123"
        assert prov["data_version"] == "1"

    def test_received_time_from_meta(self, base_obs):
        event = observation_to_event(base_obs, TWIN)
        assert event["received_time"] == "2026-09-01T10:00:00Z"

    def test_event_id_prefixed(self, base_obs):
        event = observation_to_event(base_obs, TWIN)
        assert event["event_id"] == "evt_obs-123"

    def test_missing_id_generates_uuid(self, base_obs):
        del base_obs["id"]
        event = observation_to_event(base_obs, TWIN)
        assert event["event_id"].startswith("evt_")
        assert len(event["event_id"]) > 4


# ---------------------------------------------------------------------------
# bundle_to_events
# ---------------------------------------------------------------------------

class TestBundleToEvents:

    def _make_bundle(self, entries: list[dict]) -> dict:
        return {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [{"resource": r} for r in entries],
        }

    def test_wrong_resource_type_raises(self):
        with pytest.raises(ValueError, match="Expected resourceType 'Bundle'"):
            bundle_to_events({"resourceType": "Patient"}, TWIN)

    def test_all_supported_observations_mapped(self):
        obs_size = _obs("21889-1", vq={"value": 20.0, "unit": "mm"})
        obs_grade = _obs("33732-9", vq={"value": 2})
        obs_her2 = _obs("85319-2", vcc={"text": "negative"})
        bundle = self._make_bundle([obs_size, obs_grade, obs_her2])
        events, skip_log = bundle_to_events(bundle, TWIN)
        assert len(events) == 3
        assert skip_log == []
        for e in events:
            validate_event(e)

    def test_unsupported_observation_goes_to_skip_log(self):
        bad_obs = _obs("99999-9", vq={"value": 1})
        bundle = self._make_bundle([bad_obs])
        events, skip_log = bundle_to_events(bundle, TWIN)
        assert events == []
        assert len(skip_log) == 1
        assert "Unsupported observation code" in skip_log[0]["reason"]

    def test_non_observation_entries_ignored(self):
        condition = {"resourceType": "Condition", "id": "cond-001"}
        obs = _obs("21889-1", vq={"value": 10.0, "unit": "mm"})
        bundle = self._make_bundle([condition, obs])
        events, skip_log = bundle_to_events(bundle, TWIN)
        assert len(events) == 1
        assert skip_log == []

    def test_empty_bundle_returns_empty(self):
        bundle = {"resourceType": "Bundle", "type": "collection", "entry": []}
        events, skip_log = bundle_to_events(bundle, TWIN)
        assert events == []
        assert skip_log == []

    def test_mixed_valid_invalid_observations(self):
        good = _obs("21889-1", vq={"value": 10.0, "unit": "mm"})
        bad = _obs("21889-1", vq={"value": -5.0, "unit": "mm"})
        bundle = self._make_bundle([good, bad])
        events, skip_log = bundle_to_events(bundle, TWIN)
        assert len(events) == 1
        assert len(skip_log) == 1


# ---------------------------------------------------------------------------
# Feature dictionary completeness
# ---------------------------------------------------------------------------

def test_feature_dict_covers_all_known_fields():
    expected = {
        "tumour_size_mm", "grade", "positive_nodes",
        "her2_status", "er_status", "pr_status",
        "ki67_percent", "morphology_code",
    }
    assert set(FEATURE_DICT.keys()) == expected


# ---------------------------------------------------------------------------
# Patient, Encounter, DiagnosticReport, and Synthea Bundle tests
# ---------------------------------------------------------------------------

from data.src.fhir_adapter import (
    patient_to_profile,
    encounter_to_event,
    diagnostic_report_to_events,
    synthea_bundle_to_canonical,
)


class TestPatientAdapter:

    def test_patient_to_profile_valid(self):
        patient = {
            "resourceType": "Patient",
            "id": "pat-001",
            "gender": "female",
            "birthDate": "1975-08-20",
            "identifier": [{"value": "MRN-123456"}],
        }
        profile = patient_to_profile(patient, twin_id="TWIN_001")
        assert profile["patient_id"] == "pat-001"
        assert profile["twin_id"] == "TWIN_001"
        assert profile["gender"] == "female"
        assert profile["birth_date"] == "1975-08-20"
        assert profile["mrn"] == "MRN-123456"

    def test_patient_wrong_resource_type(self):
        with pytest.raises(ValueError, match="Expected resourceType 'Patient'"):
            patient_to_profile({"resourceType": "Observation"})


class TestEncounterAdapter:

    def test_encounter_to_follow_up_event(self):
        encounter = {
            "resourceType": "Encounter",
            "id": "enc-001",
            "status": "finished",
            "class": {"code": "AMB"},
            "period": {"start": "2026-03-01T09:00:00Z"},
            "reasonCode": [{"text": "Routine surveillance examination"}],
        }
        event = encounter_to_event(encounter, TWIN)
        assert event["event_type"] == "FOLLOW_UP"
        assert event["twin_id"] == TWIN
        assert event["payload"]["encounter_class"] == "AMB"
        validate_event(event)

    def test_encounter_to_treatment_event(self):
        encounter = {
            "resourceType": "Encounter",
            "id": "enc-002",
            "status": "finished",
            "class": {"code": "AMB"},
            "period": {"start": "2026-03-01T09:00:00Z"},
            "reasonCode": [{"text": "Adjuvant Chemotherapy Cycle 1"}],
        }
        event = encounter_to_event(encounter, TWIN)
        assert event["event_type"] == "TREATMENT"
        validate_event(event)


class TestDiagnosticReportAdapter:

    def test_diagnostic_report_contained_observations(self):
        report = {
            "resourceType": "DiagnosticReport",
            "id": "dr-001",
            "status": "final",
            "effectiveDateTime": "2026-03-01T10:00:00Z",
            "conclusion": "Invasive ductal carcinoma",
            "conclusionCode": [
                {"coding": [{"system": "http://hl7.org/fhir/sid/icd-o-3", "code": "8500/3"}]}
            ],
            "contained": [
                {
                    "resourceType": "Observation",
                    "id": "obs-c-1",
                    "status": "final",
                    "code": {"coding": [{"system": "http://loinc.org", "code": "21889-1"}]},
                    "valueQuantity": {"value": 18.0, "unit": "mm"},
                }
            ],
        }
        events = diagnostic_report_to_events(report, TWIN)
        assert len(events) == 2  # 1 from contained observation, 1 from conclusion/diagnosis
        for e in events:
            validate_event(e)


class TestSyntheaBundleCanonical:

    def test_synthea_bundle_ingestion(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        bundle_path = root / "data" / "samples" / "synthea-patient-bundle.json"
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

        res = synthea_bundle_to_canonical(bundle)
        assert res["patient_profile"] is not None
        assert res["patient_profile"]["gender"] == "female"
        assert len(res["events"]) >= 7  # Encounter + DR morphology + contained obs + 5 obs
        assert res["skip_log"] == []
        for e in res["events"]:
            validate_event(e)


