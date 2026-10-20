"""
ClinicalEvent structural validator.

This module wraps the shared contract schema validator. It performs structural
(JSON Schema) validation only — it does not check clinical plausibility. Callers
are responsible for applying domain constraints before or after this check.

SHAP or model outputs must not be sourced from here. This module must not contain
patient records, trained model artefacts, or treatment logic.
"""
import argparse
import json
from pathlib import Path

from scripts.validate_contracts import validate


def validate_event(event: dict) -> None:
    """
    Validate a ClinicalEvent dict against the shared JSON Schema contract.

    Parameters
    ----------
    event : dict
        A ClinicalEvent dict to validate.

    Raises
    ------
    jsonschema.ValidationError
        If the event does not conform to contracts/clinical-event.schema.json.
    ValueError
        If 'clinical-event' is not a known contract name (internal error).
    """
    validate("clinical-event", event)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validate a ClinicalEvent JSON file against the shared schema."
    )
    parser.add_argument("event", type=Path, help="Path to a ClinicalEvent JSON file.")
    args = parser.parse_args()
    validate_event(json.loads(args.event.read_text(encoding="utf-8")))
    print("PASS ClinicalEvent (structural validation only)")
