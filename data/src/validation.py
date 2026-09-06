import argparse
import json
from pathlib import Path
from scripts.validate_contracts import validate

def validate_event(event):
    validate('clinical-event', event)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('event', type=Path)
    args = parser.parse_args()
    validate_event(json.loads(args.event.read_text()))
    print('PASS ClinicalEvent (structural validation only)')
