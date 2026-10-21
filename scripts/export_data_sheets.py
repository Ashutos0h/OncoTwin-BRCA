"""
Exports all Data Engineering datasets, feature matrices, and audit records into
Excel spreadsheets (.xlsx), CSV files (.csv), and JSON files (.json).

Outputs are written to:
- data/exports/
- data/processed/sheets/
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
import pandas as pd
import numpy as np

from data.src.acquisition import (
    acquire_metabric,
    prepare_metabric_cohort,
    evaluate_tcga_feasibility,
    generate_synthea_cohort,
)
from data.src.etl import (
    run_full_etl_pipeline,
    patient_level_three_way_split,
    generate_cohort_statistics,
    compute_missingness,
    FEATURE_KEYS,
)
from data.src.fhir_adapter import synthea_bundle_to_canonical

ROOT = Path(__file__).resolve().parents[1]
EXPORTS_DIR = ROOT / "data" / "exports"
SHEETS_DIR = ROOT / "data" / "processed" / "sheets"

EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
SHEETS_DIR.mkdir(parents=True, exist_ok=True)


def export_all():
    print("1. Preparing METABRIC Cohort...")
    df_clean, meta = prepare_metabric_cohort(horizon_months=60.0)

    # Build structured records
    records = []
    for _, row in df_clean.iterrows():
        pid = str(row["PATIENT_ID"]).strip()
        rfs_m = pd.to_numeric(row.get("RFS_MONTHS"), errors="coerce")
        rec = {
            "patient_id": pid,
            "twin_id": f"TWIN_METABRIC_{pid}",
            "tumour_size_mm": row.get("TUMOR_SIZE"),
            "grade": row.get("GRADE"),
            "positive_nodes": row.get("LYMPH_NODES_EXAMINED_POSITIVE"),
            "her2_status": row.get("HER2_STATUS"),
            "er_status": row.get("ER_STATUS"),
            "pr_status": row.get("PR_STATUS"),
            "ki67_percent": None,
            "morphology_code": "8500/3",
            "recurrence_5yr": row.get("recurrence_5yr"),
            "rfs_months": round(float(rfs_m), 1) if pd.notna(rfs_m) else None,
            "rfs_status": str(row.get("RFS_STATUS", "")).strip(),
        }
        records.append(rec)

    # Run ETL
    etl_res = run_full_etl_pipeline(records, source_name="METABRIC", data_version="metabric-v1.0.0")
    cleaned_records = etl_res["cleaned_records"]

    # Partition
    train_recs, val_recs, test_recs = patient_level_three_way_split(
        cleaned_records, patient_id_key="twin_id", train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, seed=42
    )

    train_pids = set(r["twin_id"] for r in train_recs)
    val_pids = set(r["twin_id"] for r in val_recs)
    test_pids = set(r["twin_id"] for r in test_recs)

    # Add partition column to tabular DataFrame
    df_tabular = pd.DataFrame(cleaned_records)
    if "_missing_mask" in df_tabular.columns:
        df_tabular = df_tabular.drop(columns=["_missing_mask"])

    def assign_partition(tid):
        if tid in train_pids:
            return "Train (70%)"
        elif tid in val_pids:
            return "Validation (15%)"
        elif tid in test_pids:
            return "Test (15%)"
        return "Unassigned"

    df_tabular["partition"] = df_tabular["twin_id"].apply(assign_partition)

    print(f"   -> METABRIC Tabular records: {len(df_tabular)}")

    # 2. Missingness Analysis DataFrame
    missingness = etl_res["missingness_rates"]
    df_missing = pd.DataFrame([
        {
            "feature_key": k,
            "data_type": "float" if "size" in k or "ki67" in k else ("int" if "grade" in k or "nodes" in k else "categorical"),
            "missing_count": int(df_tabular[k].isna().sum()),
            "total_count": len(df_tabular),
            "missing_fraction": round(missingness[k], 4),
            "missing_percentage": f"{round(missingness[k] * 100, 2)}%",
            "clinical_meaning": {
                "tumour_size_mm": "Maximum tumour diameter (mm)",
                "grade": "Nottingham histologic grade (1-3 + 4 undifferentiated)",
                "positive_nodes": "Number of metastatic axillary lymph nodes",
                "her2_status": "HER2 receptor status (positive/negative/equivocal)",
                "er_status": "Estrogen receptor status (positive/negative)",
                "pr_status": "Progesterone receptor status (positive/negative)",
                "ki67_percent": "Ki-67 proliferation index (%)",
                "morphology_code": "Histologic morphology (ICD-O-3)",
            }.get(k, ""),
        }
        for k in sorted(FEATURE_KEYS)
    ])

    # 3. Synthea Synthetic Cohort Tabular DataFrame
    print("2. Generating Synthea Synthetic FHIR Cohort...")
    synthea_bundles = generate_synthea_cohort(n_patients=10, seed=42)
    synthea_rows = []
    synthea_events = []
    for b in synthea_bundles:
        res = synthea_bundle_to_canonical(b)
        prof = res["patient_profile"] or {}
        events = res["events"]
        synthea_events.extend(events)

        # Extract features from events
        row = {
            "patient_id": prof.get("patient_id"),
            "twin_id": res["twin_id"],
            "mrn": prof.get("mrn"),
            "gender": prof.get("gender"),
            "birth_date": prof.get("birth_date"),
            "num_events": len(events),
        }
        for ev in events:
            payload = ev.get("payload", {})
            for pk, pv in payload.items():
                if pk in FEATURE_KEYS and pv is not None:
                    row[pk] = pv
        synthea_rows.append(row)

    df_synthea = pd.DataFrame(synthea_rows)

    # 4. TCGA-BRCA Feasibility Metrics DataFrame
    print("3. Evaluating TCGA-BRCA Feasibility Metrics...")
    tcga_rep = evaluate_tcga_feasibility()
    df_tcga = pd.DataFrame([
        {"Metric": "Dataset Name", "Value": tcga_rep["dataset"]},
        {"Metric": "External Validation Feasible", "Value": str(tcga_rep["feasible"])},
        {"Metric": "Total Patients in Registry", "Value": tcga_rep["n_total_patients"]},
        {"Metric": "Patients with Disease-Free Follow-up", "Value": tcga_rep["n_with_dfs_data"]},
        {"Metric": "Median DFS Follow-up (Months)", "Value": tcga_rep["median_followup_months"]},
        {"Metric": "Patients Censored Before 60 Months", "Value": tcga_rep["n_censored_before_60_months"]},
        {"Metric": "Censoring Percentage (< 5 Years)", "Value": f"{tcga_rep['censored_percentage']}%"},
        {"Metric": "Continuous Tumour Size (mm)", "Value": "Not captured (Pathologic T-stage T1-T4 only)"},
        {"Metric": "Nottingham Histologic Grade", "Value": "Missing for > 75% of public cohort"},
        {"Metric": "Scientific Conclusion", "Value": tcga_rep["conclusion"]},
    ])

    # 5. Canonical Entities Catalog DataFrame
    df_catalog = pd.DataFrame([
        {"Entity": "Twin", "Description": "Digital-twin lifecycle anchor entity", "Primary_Key": "twin_id", "Storage": "SQL Table (twins)"},
        {"Entity": "PatientProfile", "Description": "Patient demographics and MRN", "Primary_Key": "patient_id", "Storage": "SQL Table (patient_profiles)"},
        {"Entity": "ClinicalEvent", "Description": "Immutable event (Pathology, Biomarker, Diagnosis, Treatment, Follow-up)", "Primary_Key": "event_id", "Storage": "SQL Table (clinical_events, JSONB)"},
        {"Entity": "Observation", "Description": "Granular clinical observation with LOINC code and unit", "Primary_Key": "observation_id", "Storage": "SQL Table (observations)"},
        {"Entity": "TumourProfile", "Description": "Harmonized 8-feature representation", "Primary_Key": "profile_id", "Storage": "SQL Table (tumour_profiles)"},
        {"Entity": "FeatureSnapshot", "Description": "Point-in-time snapshot with state version lineage", "Primary_Key": "snapshot_id", "Storage": "SQL Table (feature_snapshots, JSONB)"},
        {"Entity": "Prediction", "Description": "Prognostic risk estimate with TreeSHAP values", "Primary_Key": "prediction_id", "Storage": "SQL Table (predictions, JSONB)"},
        {"Entity": "ModelVersion", "Description": "Registered AI/ML algorithm metadata and metrics", "Primary_Key": "model_id", "Storage": "SQL Table (model_versions)"},
        {"Entity": "DataVersion", "Description": "Dataset provenance and SHA-256 fingerprint", "Primary_Key": "data_version_id", "Storage": "SQL Table (data_versions)"},
        {"Entity": "AuditLog", "Description": "Tamper-evident audit ledger connecting all actions", "Primary_Key": "audit_id", "Storage": "SQL Table (audit_records)"},
    ])

    # 6. Sample Canonical Events DataFrame
    sample_events_rows = []
    for ev in synthea_events[:25]:
        sample_events_rows.append({
            "event_id": ev["event_id"],
            "twin_id": ev["twin_id"],
            "event_type": ev["event_type"],
            "effective_time": ev["effective_time"],
            "source": ev["source"],
            "quality_status": ev["quality_status"],
            "source_record_id": ev["provenance"]["source_record_id"],
            "payload_json": json.dumps(ev["payload"]),
        })
    df_events = pd.DataFrame(sample_events_rows)

    # -----------------------------------------------------------------------
    # WRITE EXCEL WORKBOOKS
    # -----------------------------------------------------------------------
    print("4. Writing Master Multi-Sheet Excel Workbook...")
    master_xlsx = EXPORTS_DIR / "OncoTwin_BRCA_Data_Foundation.xlsx"
    with pd.ExcelWriter(master_xlsx, engine="openpyxl") as writer:
        df_catalog.to_excel(writer, sheet_name="Entities_Catalog", index=False)
        df_missing.to_excel(writer, sheet_name="Missingness_Analysis", index=False)
        df_tabular.to_excel(writer, sheet_name="METABRIC_Cleaned_Cohort", index=False)
        df_synthea.to_excel(writer, sheet_name="Synthea_FHIR_Cohort", index=False)
        df_tcga.to_excel(writer, sheet_name="TCGA_Feasibility_Report", index=False)
        df_events.to_excel(writer, sheet_name="Canonical_Events_Sample", index=False)

    # Copy to data/processed/sheets/ as well
    import shutil
    shutil.copy(master_xlsx, SHEETS_DIR / "OncoTwin_BRCA_Data_Foundation.xlsx")

    # Write Individual CSV files
    print("5. Writing Individual CSV files...")
    df_tabular.to_csv(EXPORTS_DIR / "metabric_cleaned_cohort.csv", index=False)
    df_missing.to_csv(EXPORTS_DIR / "feature_missingness_summary.csv", index=False)
    df_synthea.to_csv(EXPORTS_DIR / "synthea_synthetic_cohort.csv", index=False)
    df_tcga.to_csv(EXPORTS_DIR / "tcga_feasibility_metrics.csv", index=False)
    df_catalog.to_csv(EXPORTS_DIR / "canonical_entities_catalog.csv", index=False)
    df_events.to_csv(EXPORTS_DIR / "canonical_events_sample.csv", index=False)

    # Write Individual JSON files
    print("6. Writing Individual JSON files...")
    (EXPORTS_DIR / "metabric_cleaned_cohort.json").write_text(
        df_tabular.to_json(orient="records", indent=2), encoding="utf-8"
    )
    (EXPORTS_DIR / "feature_missingness_summary.json").write_text(
        df_missing.to_json(orient="records", indent=2), encoding="utf-8"
    )
    (EXPORTS_DIR / "synthea_synthetic_cohort.json").write_text(
        df_synthea.to_json(orient="records", indent=2), encoding="utf-8"
    )
    (EXPORTS_DIR / "tcga_feasibility_metrics.json").write_text(
        json.dumps(tcga_rep, indent=2), encoding="utf-8"
    )
    (EXPORTS_DIR / "canonical_entities_catalog.json").write_text(
        df_catalog.to_json(orient="records", indent=2), encoding="utf-8"
    )
    (EXPORTS_DIR / "canonical_events_sample.json").write_text(
        json.dumps(synthea_events[:25], indent=2), encoding="utf-8"
    )

    print("\n[SUCCESS] All data sheets exported successfully to:")
    print(f"  Excel Master: {master_xlsx}")
    print(f"  Export Folder: {EXPORTS_DIR}")


if __name__ == "__main__":
    export_all()
