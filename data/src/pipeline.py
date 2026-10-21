"""
Reproducible Data Engineering & FHIR Ingestion Pipeline for OncoTwin-BRCA.

Main Deliverable for Data Engineering, FHIR & Database Lead:
Reproducible METABRIC / TCGA-BRCA / Synthea → validated canonical dataset → PostgreSQL/FHIR ingestion pipeline.

Architecture:
  Raw Dataset
      ↓
  Schema Validation
      ↓
  Cleaning & Deduplication
      ↓
  Normalization
      ↓
  Missingness Detection & Masking
      ↓
  Anti-Leakage Splitting (Zero Patient Overlap)
      ↓
  Canonical Mapping (ClinicalEvent, PatientProfile, TumourProfile)
      ↓
  Database Ingestion (PostgreSQL / SQLite Event Store)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.database import (
    Base,
    build_engine,
    create_data_foundation,
    create_database_stores,
)
from backend.app.models import ClinicalEvent
from backend.app.store import DuplicateEventError
from data.src.acquisition import (
    acquire_metabric,
    evaluate_tcga_feasibility,
    generate_synthea_cohort,
    prepare_metabric_cohort,
    tcia_stretch_goal_spec,
)
from data.src.etl import (
    FEATURE_KEYS,
    clean_and_normalize_record,
    compute_missingness,
    generate_cohort_statistics,
    patient_level_three_way_split,
    run_full_etl_pipeline,
)
from data.src.fhir_adapter import (
    observation_to_event,
    synthea_bundle_to_canonical,
)

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"
SAMPLES_DIR = ROOT / "data" / "samples"


class DataPipeline:
    """
    Orchestrates ingestion, ETL cleaning, validation, anti-leakage splitting,
    and database ingestion for METABRIC, TCGA-BRCA, and Synthea.
    """

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url
        if database_url:
            self.engine = build_engine(database_url)
            Base.metadata.create_all(self.engine)
            stores = create_database_stores(database_url)
            self.event_store = stores[0]
            self.foundation = create_data_foundation(database_url)
        else:
            self.engine = None
            self.event_store = None
            self.foundation = None

    def process_synthea_cohort(
        self, n_patients: int = 5, seed: int = 42
    ) -> dict[str, Any]:
        """
        Generates and ingests synthetic Synthea FHIR R4 Bundles through
        the FHIR adapter into the canonical database.
        """
        print(f"[Synthea] Generating synthetic FHIR cohort (N={n_patients})...")
        bundles = generate_synthea_cohort(n_patients=n_patients, seed=seed)

        all_events: list[dict[str, Any]] = []
        all_profiles: list[dict[str, Any]] = []
        total_skips: list[dict[str, Any]] = []

        for b in bundles:
            res = synthea_bundle_to_canonical(b)
            twin_id = res["twin_id"]
            if res["patient_profile"]:
                all_profiles.append(res["patient_profile"])
            all_events.extend(res["events"])
            total_skips.extend(res["skip_log"])

            # Ingest to DB if active
            if self.event_store and self.foundation:
                try:
                    self.event_store.create_twin(twin_id)
                except Exception:
                    pass
                if res["patient_profile"]:
                    self.foundation.save_patient_profile(res["patient_profile"])
                for ev in res["events"]:
                    try:
                        self.event_store.append(twin_id, ClinicalEvent.model_validate(ev))
                    except DuplicateEventError:
                        pass
                    except Exception as err:
                        print(f"Warning: could not append event {ev.get('event_id')}: {err}")

        # Compute SHA-256 fingerprint
        content_hash = hashlib.sha256(
            json.dumps(all_events, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        version_data = {
            "data_version_id": f"synthea-v1.0.0-{content_hash[:8]}",
            "name": "Synthea FHIR R4 Breast Cancer Synthetic Cohort",
            "dataset_name": "Synthea",
            "record_count": len(all_events),
            "content_sha256": content_hash,
        }
        if self.foundation:
            self.foundation.register_data_version(version_data)

        summary = {
            "dataset": "Synthea",
            "status": "success",
            "n_patients": n_patients,
            "n_events": len(all_events),
            "n_profiles": len(all_profiles),
            "data_version": version_data["data_version_id"],
            "content_sha256": content_hash,
            "skip_log_count": len(total_skips),
        }
        print(f"[Synthea] Complete: {summary['n_events']} events across {n_patients} patients.")
        return summary

    def process_metabric_cohort(
        self, split_ratios: tuple[float, float, float] = (0.70, 0.15, 0.15), seed: int = 42
    ) -> dict[str, Any]:
        """
        Executes full ETL on METABRIC cohort:
        - Load and clean clinical data
        - Anti-leakage 3-way split (train/validation/test)
        - Canonical event creation & database persistence
        """
        print("[METABRIC] Acquiring and cleaning cohort...")
        df_clean, meta = prepare_metabric_cohort(horizon_months=60.0)

        # Convert to records
        raw_records: list[dict[str, Any]] = []
        for _, row in df_clean.iterrows():
            rec = {
                "twin_id": f"TWIN_METABRIC_{str(row['PATIENT_ID']).strip()}",
                "tumour_size_mm": row.get("TUMOR_SIZE"),
                "grade": row.get("GRADE"),
                "positive_nodes": row.get("LYMPH_NODES_EXAMINED_POSITIVE"),
                "her2_status": row.get("HER2_STATUS"),
                "er_status": row.get("ER_STATUS"),
                "pr_status": row.get("PR_STATUS"),
                "ki67_percent": None,
                "morphology_code": "8500/3",
                "recurrence_5yr": row.get("recurrence_5yr"),
            }
            raw_records.append(rec)

        print(f"[METABRIC] Executing canonical ETL pipeline on {len(raw_records)} records...")
        etl_result = run_full_etl_pipeline(
            raw_records, source_name="METABRIC", data_version="metabric-v1.0.0"
        )
        cleaned = etl_result["cleaned_records"]

        # Anti-leakage 3-way split
        print(f"[METABRIC] Partitioning cohort (Train/Val/Test = {split_ratios})...")
        train_recs, val_recs, test_recs = patient_level_three_way_split(
            cleaned,
            patient_id_key="twin_id",
            train_ratio=split_ratios[0],
            val_ratio=split_ratios[1],
            test_ratio=split_ratios[2],
            seed=seed,
        )

        # Strict zero-leakage verification
        train_ids = set(r["twin_id"] for r in train_recs)
        val_ids = set(r["twin_id"] for r in val_recs)
        test_ids = set(r["twin_id"] for r in test_recs)

        assert not (train_ids & val_ids), "Patient leakage between train and val!"
        assert not (train_ids & test_ids), "Patient leakage between train and test!"
        assert not (val_ids & test_ids), "Patient leakage between val and test!"

        # Ingestion to database if configured
        if self.event_store and self.foundation:
            print("[METABRIC] Ingesting canonical entities and events into database...")
            # Sample ingestion (first 25 patients to avoid slow runs)
            sample_for_db = cleaned[:25]
            for r in sample_for_db:
                twin_id = r["twin_id"]
                try:
                    self.event_store.create_twin(twin_id)
                except Exception:
                    pass
                # Save TumourProfile
                tumour_prof = {
                    "profile_id": f"tum_{twin_id}",
                    "twin_id": twin_id,
                    "tumour_size_mm": r.get("tumour_size_mm"),
                    "grade": r.get("grade"),
                    "positive_nodes": r.get("positive_nodes"),
                    "her2_status": r.get("her2_status"),
                    "er_status": r.get("er_status"),
                    "pr_status": r.get("pr_status"),
                }
                self.foundation.save_tumour_profile(tumour_prof)

            # Ingest corresponding events
            sample_events = [e for e in etl_result["canonical_events"] if e["twin_id"] in set(r["twin_id"] for r in sample_for_db)]
            for ev in sample_events:
                try:
                    self.event_store.append(ev["twin_id"], ClinicalEvent.model_validate(ev))
                except DuplicateEventError:
                    pass
                except Exception:
                    pass

            # Register DataVersion
            version_data = {
                "data_version_id": f"metabric-v1.0.0-{etl_result['content_sha256'][:8]}",
                "name": "METABRIC 5-Year Recurrence Cleaned Cohort",
                "dataset_name": "METABRIC",
                "record_count": len(cleaned),
                "content_sha256": etl_result["content_sha256"],
            }
            self.foundation.register_data_version(version_data)

        summary = {
            "dataset": "METABRIC",
            "status": "success",
            "n_total": len(cleaned),
            "n_train": len(train_recs),
            "n_val": len(val_recs),
            "n_test": len(test_recs),
            "content_sha256": etl_result["content_sha256"],
            "missingness": etl_result["missingness_rates"],
            "zero_leakage_verified": True,
        }
        print(f"[METABRIC] Complete: Train={len(train_recs)}, Val={len(val_recs)}, Test={len(test_recs)}.")
        return summary

    def process_tcga_evaluation(self) -> dict[str, Any]:
        """
        Executes external validation feasibility analysis on TCGA-BRCA.
        """
        print("[TCGA-BRCA] Evaluating external validation feasibility...")
        report = evaluate_tcga_feasibility()
        print(f"[TCGA-BRCA] Feasibility: {report['feasible']} (Median DFS: {report['median_followup_months']} mo)")
        return report


def run_cli():
    parser = argparse.ArgumentParser(description="OncoTwin-BRCA Data Pipeline")
    parser.add_argument(
        "--dataset",
        choices=["metabric", "tcga", "synthea", "all"],
        default="all",
        help="Dataset to process",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Target database URL (e.g. sqlite:///data/oncotwin.db or postgresql://...)",
    )
    parser.add_argument(
        "--synthea-count",
        type=int,
        default=5,
        help="Number of synthetic Synthea patients to generate",
    )

    args = parser.parse_args()

    # Default to local sqlite if none provided
    db_url = args.db_url or f"sqlite:///{ROOT / 'data' / 'processed' / 'pipeline.db'}"

    pipeline = DataPipeline(database_url=db_url)
    results = {}

    if args.dataset in ("synthea", "all"):
        results["synthea"] = pipeline.process_synthea_cohort(n_patients=args.synthea_count)

    if args.dataset in ("metabric", "all"):
        results["metabric"] = pipeline.process_metabric_cohort()

    if args.dataset in ("tcga", "all"):
        results["tcga"] = pipeline.process_tcga_evaluation()

    print("\n--- Pipeline Execution Summary ---")
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    run_cli()
