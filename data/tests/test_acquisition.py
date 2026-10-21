"""
Unit tests for data.src.acquisition — METABRIC, TCGA, Synthea, and TCIA handlers.
"""
from pathlib import Path
import pytest

from data.src.acquisition import (
    acquire_metabric,
    evaluate_tcga_feasibility,
    generate_synthea_cohort,
    prepare_metabric_cohort,
    tcia_stretch_goal_spec,
)


class TestAcquisition:

    def test_generate_synthea_cohort(self):
        bundles = generate_synthea_cohort(n_patients=3, seed=123)
        assert len(bundles) == 3
        for b in bundles:
            assert b["resourceType"] == "Bundle"
            res_types = [entry["resource"]["resourceType"] for entry in b["entry"]]
            assert "Patient" in res_types
            assert "Encounter" in res_types
            assert "DiagnosticReport" in res_types
            assert "Observation" in res_types

    def test_evaluate_tcga_feasibility(self):
        report = evaluate_tcga_feasibility()
        assert report["dataset"] == "TCGA-BRCA"
        assert report["feasible"] is False
        assert report["median_followup_months"] <= 30.0
        assert report["censored_percentage"] >= 65.0
        assert len(report["primary_blockers"]) >= 3

    def test_tcia_stretch_goal_spec(self):
        spec = tcia_stretch_goal_spec()
        assert spec["status"] == "stretch_goal"
        assert "MR" in spec["imaging_modalities"]
        assert "radiomic_tumour_volume_cm3" in spec["planned_features"]
        assert spec["ingestion_contract"]["event_type"] == "IMAGING_STUDY"

    def test_prepare_metabric_cohort(self):
        # Checks exclusion and target definitions
        df_clean, meta = prepare_metabric_cohort(horizon_months=60.0)
        assert len(df_clean) > 1000
        assert "recurrence_5yr" in df_clean.columns
        assert set(df_clean["recurrence_5yr"].unique()).issubset({0, 1})
        assert meta["n_analyzed"] == len(df_clean)
        assert meta["n_recurrences"] > 0
