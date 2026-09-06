import json
import pytest
from jsonschema import ValidationError
from scripts.validate_contracts import ROOT, load_example
from data.src.validation import validate_event

def test_sample_matches_contract_fixture():
    sample = json.loads((ROOT / 'data/samples/pathology-event.json').read_text())
    validate_event(sample)
    assert sample == load_example('clinical-event')

def test_invalid_event_type_rejected():
    event = load_example('clinical-event')
    event['event_type'] = 'unsupported'
    with pytest.raises(ValidationError):
        validate_event(event)
