"""Constant synthetic response for integration only; no trained inference."""
import argparse
import json
from pathlib import Path
from scripts.validate_contracts import load_example, validate

def predict_demo(snapshot, *, prediction_id, audit_id, created_at):
    validate('feature-snapshot', snapshot)
    result = load_example('prediction')
    for key in ('twin_id', 'snapshot_id', 'state_version', 'data_version'):
        result[key] = snapshot[key]
    result.update(prediction_id=prediction_id, audit_id=audit_id, created_at=created_at)
    validate('prediction', result)
    return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    result = predict_demo(json.loads(args.snapshot.read_text()), prediction_id='pred_demo_001',
                          audit_id='audit_demo_001', created_at='2026-09-01T10:00:00Z')
    print(json.dumps(result, indent=2))
