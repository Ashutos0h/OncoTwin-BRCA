import pytest
from jsonschema import ValidationError
from scripts.validate_contracts import NAMES, load_example, validate

@pytest.mark.parametrize('name', NAMES)
def test_examples(name):
    validate(name, load_example(name))

@pytest.mark.parametrize('name', NAMES)
def test_missing_identity_rejected(name):
    value = load_example(name)
    del value['twin_id']
    with pytest.raises(ValidationError):
        validate(name, value)

@pytest.mark.parametrize('field,value', [('risk_probability', 1.1), ('created_at', 'yesterday'), ('state_version', 0)])
def test_invalid_prediction_rejected(field, value):
    prediction = load_example('prediction')
    prediction[field] = value
    with pytest.raises(ValidationError):
        validate('prediction', prediction)

def test_fixture_lineage():
    e, s, f, p, a = [load_example(n) for n in NAMES]
    assert len({v['twin_id'] for v in (e, s, f, p, a)}) == 1
    assert s['event_ids'] == a['event_ids'] == [e['event_id']]
    assert s['values'] == f['features'] == e['payload']
    assert s['missing_fields'] == f['missing_fields'] == ['her2_status']
    assert s['state_version'] == f['state_version'] == p['state_version'] == a['state_version']
    assert e['provenance']['data_version'] == s['data_version'] == f['data_version'] == p['data_version'] == a['data_version']
    assert f['snapshot_id'] == p['snapshot_id'] == a['snapshot_id']
    assert p['prediction_id'] == a['prediction_id']
    assert p['audit_id'] == a['audit_id']
    assert p['model_version'] == a['model_version']
