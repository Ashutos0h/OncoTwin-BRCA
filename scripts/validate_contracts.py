"""Validate shared JSON schemas and their synthetic fixtures."""
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('clinical-event', 'twin-state', 'feature-snapshot', 'prediction', 'audit-record')

def load_example(name):
    return json.loads((ROOT / 'contracts' / 'examples' / f'{name}.json').read_text())

def validate(name, value):
    if name not in NAMES:
        raise ValueError(f'Unknown contract: {name}')
    schema = json.loads((ROOT / 'contracts' / f'{name}.schema.json').read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)

if __name__ == '__main__':
    for name in NAMES:
        validate(name, load_example(name))
        print(f'PASS {name}')
