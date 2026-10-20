"""
Tests for data.src.validation — ClinicalEvent structural validation.
"""
import json
import copy
import pytest
from jsonschema import ValidationError
from scripts.validate_contracts import ROOT, load_example
from data.src.validation import validate_event


def test_sample_matches_contract_fixture():
    """data/samples/pathology-event.json must match the contract example exactly."""
    sample = json.loads((ROOT / "data/samples/pathology-event.json").read_text())
    validate_event(sample)
    assert sample == load_example("clinical-event")


def test_contract_example_validates():
    """contracts/examples/clinical-event.json must pass validation."""
    example = load_example("clinical-event")
    validate_event(example)  # must not raise


def test_invalid_event_type_rejected():
    event = load_example("clinical-event")
    event["event_type"] = "unsupported"
    with pytest.raises(ValidationError):
        validate_event(event)


def test_missing_required_field_rejected():
    event = load_example("clinical-event")
    del event["twin_id"]
    with pytest.raises(ValidationError):
        validate_event(event)


def test_empty_twin_id_rejected():
    event = load_example("clinical-event")
    event["twin_id"] = ""
    with pytest.raises(ValidationError):
        validate_event(event)


def test_invalid_quality_status_rejected():
    event = load_example("clinical-event")
    event["quality_status"] = "unknown_status"
    with pytest.raises(ValidationError):
        validate_event(event)


def test_empty_payload_rejected():
    event = load_example("clinical-event")
    event["payload"] = {}
    with pytest.raises(ValidationError):
        validate_event(event)


def test_additional_top_level_property_rejected():
    event = load_example("clinical-event")
    event["extra_field"] = "not allowed"
    with pytest.raises(ValidationError):
        validate_event(event)


def test_all_valid_event_types_accepted():
    valid_types = ["PATHOLOGY_RESULT", "DIAGNOSIS", "BIOMARKER_RESULT", "TREATMENT", "FOLLOW_UP"]
    base = load_example("clinical-event")
    for et in valid_types:
        event = copy.deepcopy(base)
        event["event_type"] = et
        validate_event(event)  # must not raise


def test_null_payload_values_accepted():
    """Payload values may be null (represents missingness)."""
    event = load_example("clinical-event")
    event["payload"]["her2_status"] = None
    validate_event(event)  # must not raise


def test_warning_quality_status_accepted():
    event = load_example("clinical-event")
    event["quality_status"] = "warning"
    validate_event(event)
