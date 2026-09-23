"""Cohort ingestion boundary."""
import json
from pathlib import Path

def run_etl(source_file: str):
    """
    Ingests a synthetic cohort from a JSON file.
    License: Synthetic Data (MIT)
    Source: Mock generation script
    Data Dictionary: { 'tumour_size_mm': float, 'grade': int, 'positive_nodes': int }
    """
    path = Path(source_file)
    if not path.exists():
        raise FileNotFoundError(f"Cohort source {source_file} not found.")
    
    with open(path, 'r') as f:
        cohort = json.load(f)
        
    if not isinstance(cohort, list):
        raise ValueError("Expected cohort to be a list of records")
        
    return cohort
