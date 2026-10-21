"""
Integration tests for data.src.pipeline — Full ETL and database ingestion pipeline.
"""
from pathlib import Path
import pytest

from data.src.pipeline import DataPipeline


class TestDataPipeline:

    def test_pipeline_synthea_and_database_ingestion(self, tmp_path):
        db_path = tmp_path / "test_pipeline.db"
        db_url = f"sqlite+pysqlite:///{db_path.as_posix()}"

        pipeline = DataPipeline(database_url=db_url)
        summary = pipeline.process_synthea_cohort(n_patients=3, seed=42)

        assert summary["status"] == "success"
        assert summary["n_patients"] == 3
        assert summary["n_events"] > 0
        assert summary["data_version"].startswith("synthea-v1.0.0")

        # Verify twins were persisted
        twins, total = pipeline.event_store.list_twins(limit=10, offset=0)
        assert total == 3

    def test_pipeline_tcga_feasibility(self):
        pipeline = DataPipeline()
        report = pipeline.process_tcga_evaluation()
        assert report["dataset"] == "TCGA-BRCA"
        assert report["feasible"] is False

    def test_three_way_anti_leakage_split(self):
        records = [
            {"twin_id": f"TWIN_{i:02d}", "tumour_size_mm": 20.0, "grade": 2}
            for i in range(1, 21)
        ]
        from data.src.etl import patient_level_three_way_split

        train, val, test = patient_level_three_way_split(
            records, train_ratio=0.7, val_ratio=0.15, test_ratio=0.15, seed=42
        )
        assert len(train) + len(val) + len(test) == 20

        train_ids = set(r["twin_id"] for r in train)
        val_ids = set(r["twin_id"] for r in val)
        test_ids = set(r["twin_id"] for r in test)

        assert len(train_ids & val_ids) == 0
        assert len(train_ids & test_ids) == 0
        assert len(val_ids & test_ids) == 0
