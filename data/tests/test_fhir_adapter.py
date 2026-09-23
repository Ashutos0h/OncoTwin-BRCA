import pytest
from data.src.fhir_adapter import observation_to_event
from data.src.validation import validate_event

@pytest.fixture
def valid_fhir_observation():
    return {
        "resourceType": "Observation",
        "id": "obs-123",
        "status": "final",
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": "21889-1",
                    "display": "Size Tumor"
                }
            ]
        },
        "subject": {
            "reference": "Patient/SYNTHETIC_TWIN_001"
        },
        "effectiveDateTime": "2026-09-01T10:00:00Z",
        "valueQuantity": {
            "value": 31.0,
            "unit": "mm",
            "system": "http://unitsofmeasure.org",
            "code": "mm"
        },
        "meta": {
            "versionId": "1",
            "lastUpdated": "2026-09-01T10:00:00Z"
        }
    }

def test_observation_to_event_valid(valid_fhir_observation):
    event = observation_to_event(valid_fhir_observation, "SYNTHETIC_TWIN_001")
    validate_event(event) # Should pass schema validation
    assert event["payload"]["tumour_size_mm"] == 31.0
    assert event["twin_id"] == "SYNTHETIC_TWIN_001"
    assert event["event_type"] == "PATHOLOGY_RESULT"

def test_observation_to_event_invalid_code(valid_fhir_observation):
    valid_fhir_observation["code"]["coding"][0]["code"] = "99999-9"
    with pytest.raises(ValueError, match="Unsupported observation code"):
        observation_to_event(valid_fhir_observation, "SYNTHETIC_TWIN_001")

def test_observation_to_event_cm_unit(valid_fhir_observation):
    valid_fhir_observation["valueQuantity"]["unit"] = "cm"
    valid_fhir_observation["valueQuantity"]["value"] = 3.1
    event = observation_to_event(valid_fhir_observation, "SYNTHETIC_TWIN_001")
    assert event["payload"]["tumour_size_mm"] == 31.0

def test_observation_to_event_invalid_unit(valid_fhir_observation):
    valid_fhir_observation["valueQuantity"]["unit"] = "inch"
    with pytest.raises(ValueError, match="Unsupported unit"):
        observation_to_event(valid_fhir_observation, "SYNTHETIC_TWIN_001")

def test_observation_to_event_negative_value(valid_fhir_observation):
    valid_fhir_observation["valueQuantity"]["value"] = -5.0
    with pytest.raises(ValueError, match="Impossible or missing value"):
        observation_to_event(valid_fhir_observation, "SYNTHETIC_TWIN_001")
