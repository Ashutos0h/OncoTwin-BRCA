from copy import deepcopy
import pytest
from jsonschema import ValidationError
from scripts.validate_contracts import load_example, validate
from ml.src.predict import predict_demo

def test_mock_preserves_lineage_and_input():
    snapshot = load_example('feature-snapshot')
    snapshot.update(twin_id='SYNTHETIC_OTHER', snapshot_id='snapshot_other', state_version=2, data_version='synthetic-2')
    before = deepcopy(snapshot)
    kwargs = dict(prediction_id='pred_other', audit_id='audit_other', created_at='2026-09-02T00:00:00Z')
    result = predict_demo(snapshot, **kwargs)
    validate('prediction', result)
    assert result == predict_demo(snapshot, **kwargs)
    assert snapshot == before
    for field in ('twin_id', 'snapshot_id', 'state_version', 'data_version'):
        assert result[field] == snapshot[field]
    assert result['audit_id'] == 'audit_other'
    assert result['is_mock'] is True
    assert result['confidence'] == 'not_assessed'
    assert result['ood_flag'] is None

def test_invalid_input_rejected():
    with pytest.raises(ValidationError):
        predict_demo({}, prediction_id='p', audit_id='a', created_at='2026-09-02T00:00:00Z')
