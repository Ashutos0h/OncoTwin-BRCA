"""
Script to compile OncoTwin_BRCA_paper.md into a professional, publication-ready
Microsoft Word (.docx) document formatted with IEEE-style academic formatting,
including tables, figures, metadata, and references.
"""
from pathlib import Path
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml, OxmlElement
from docx.oxml.ns import nsdecls, qn

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs" / "paper"
FIGURES_DIR = ROOT / "docs" / "figures"
DATASET_DIR = ROOT / "DataSet"

OUTPUT_DOCX = DOCS_DIR / "OncoTwin_BRCA_paper.docx"
DATASET_DOCX = DATASET_DIR / "OncoTwin_BRCA_paper.docx"

# Palette
COLOR_NAVY = RGBColor(0x1B, 0x36, 0x5D)
COLOR_STEEL = RGBColor(0x2B, 0x4C, 0x7E)
COLOR_DARK = RGBColor(0x1F, 0x29, 0x37)
COLOR_GRAY = RGBColor(0x4B, 0x55, 0x63)
HEX_NAVY = "1B365D"
HEX_LIGHT_GRAY = "F3F4F6"
HEX_BORDER = "D1D5DB"
HEX_WHITE = "FFFFFF"


def set_cell_shading(cell, color_hex):
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shd)


def set_cell_margins(cell, top=120, bottom=120, left=160, right=160):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(
        f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>'
    )
    tcPr.append(tcMar)


def set_table_borders(table, color="D1D5DB", sz="4", val="single"):
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'  <w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:left w:val="none"/>'
        f'  <w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:right w:val="none"/>'
        f'  <w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'  <w:insideV w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)


def format_table(table, col_widths, headers, data, alignments=None):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(table)

    # Header Row
    hdr_cells = table.rows[0].cells
    for i, title in enumerate(headers):
        hdr_cells[i].text = title
        set_cell_shading(hdr_cells[i], HEX_NAVY)
        set_cell_margins(hdr_cells[i], top=140, bottom=140, left=160, right=160)
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if (alignments and alignments[i] == "center") else WD_ALIGN_PARAGRAPH.LEFT
        for run in p.runs:
            run.font.name = "Calibri"
            run.font.size = Pt(9.5)
            run.font.bold = True
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    # Data Rows
    for r_idx, row_data in enumerate(data):
        row_cells = table.rows[r_idx + 1].cells
        bg_color = HEX_LIGHT_GRAY if r_idx % 2 == 1 else HEX_WHITE
        for c_idx, val in enumerate(row_data):
            row_cells[c_idx].text = str(val)
            set_cell_shading(row_cells[c_idx], bg_color)
            set_cell_margins(row_cells[c_idx], top=100, bottom=100, left=160, right=160)
            p = row_cells[c_idx].paragraphs[0]
            if alignments and alignments[c_idx] == "center":
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            for run in p.runs:
                run.font.name = "Calibri"
                run.font.size = Pt(9.0)
                run.font.color.rgb = COLOR_DARK
                if c_idx == 0:
                    run.font.bold = True

    # Column widths
    for row in table.rows:
        for idx, width in enumerate(col_widths):
            row.cells[idx].width = width


def add_figure_with_caption(doc, image_path, caption_text, width=Inches(6.0)):
    if Path(image_path).exists():
        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_img.paragraph_format.space_before = Pt(12)
        p_img.paragraph_format.space_after = Pt(4)
        run_img = p_img.add_run()
        run_img.add_picture(str(image_path), width=width)

        p_cap = doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_cap.paragraph_format.space_before = Pt(0)
        p_cap.paragraph_format.space_after = Pt(14)
        run_cap = p_cap.add_run(caption_text)
        run_cap.font.name = "Calibri"
        run_cap.font.size = Pt(9.0)
        run_cap.font.italic = True
        run_cap.font.color.rgb = COLOR_GRAY


def build_word_document():
    doc = docx.Document()

    # Set page margins (1 inch)
    sections = doc.sections
    for section in sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    # Set Normal Style font
    style_normal = doc.styles["Normal"]
    style_normal.font.name = "Calibri"
    style_normal.font.size = Pt(10.5)
    style_normal.font.color.rgb = COLOR_DARK

    # =========================================================================
    # TITLE & AUTHORS
    # =========================================================================
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(0)
    p_title.paragraph_format.space_after = Pt(8)
    run_title = p_title.add_run(
        "OncoTwin-BRCA: An Event-Sourced Patient-State Prototype for Traceable Breast-Cancer Recurrence Risk Estimation"
    )
    run_title.font.name = "Calibri"
    run_title.font.size = Pt(18)
    run_title.font.bold = True
    run_title.font.color.rgb = COLOR_NAVY

    p_authors = doc.add_paragraph()
    p_authors.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_authors.paragraph_format.space_before = Pt(0)
    p_authors.paragraph_format.space_after = Pt(4)
    run_auth = p_authors.add_run("Ashutosh Verma, Shivansh Vats, Rajat Bhardwaj, and Bhumika Upreti")
    run_auth.font.bold = True
    run_auth.font.size = Pt(11)

    p_affil = doc.add_paragraph()
    p_affil.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_affil.paragraph_format.space_before = Pt(0)
    p_affil.paragraph_format.space_after = Pt(4)
    run_affil = p_affil.add_run(
        "Department of Computer Science & Engineering (Artificial Intelligence)\n"
        "ABES Institute of Technology, Ghaziabad, Uttar Pradesh, India"
    )
    run_affil.font.size = Pt(9.5)
    run_affil.font.italic = True
    run_affil.font.color.rgb = COLOR_GRAY

    p_meta = doc.add_paragraph()
    p_meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_meta.paragraph_format.space_before = Pt(0)
    p_meta.paragraph_format.space_after = Pt(16)
    run_meta = p_meta.add_run(
        "Supervisor: Dr. Vineet Kumar Singh | Contact: vashutosh685@gmail.com\n"
        "Research Prototype — Not a Medical Device"
    )
    run_meta.font.size = Pt(8.5)
    run_meta.font.color.rgb = COLOR_GRAY

    # =========================================================================
    # ABSTRACT & INDEX TERMS CALLOUT
    # =========================================================================
    table_abs = doc.add_table(rows=1, cols=1)
    table_abs.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell_abs = table_abs.rows[0].cells[0]
    set_cell_shading(cell_abs, HEX_LIGHT_GRAY)
    set_cell_margins(cell_abs, top=180, bottom=180, left=220, right=220)
    
    # Border: left navy bar, no top/bottom/right
    tcPr = cell_abs._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'  <w:top w:val="none"/>'
        f'  <w:left w:val="single" w:sz="24" w:space="0" w:color="{HEX_NAVY}"/>'
        f'  <w:bottom w:val="none"/>'
        f'  <w:right w:val="none"/>'
        f'</w:tcBorders>'
    )
    tcPr.append(borders)
    cell_abs.width = Inches(6.5)

    p_abs = cell_abs.paragraphs[0]
    p_abs.paragraph_format.space_before = Pt(0)
    p_abs.paragraph_format.space_after = Pt(6)
    p_abs.paragraph_format.line_spacing = 1.15
    run_ab_bold = p_abs.add_run("Abstract—")
    run_ab_bold.font.bold = True
    run_ab_bold.font.size = Pt(9.5)
    run_ab_bold.font.color.rgb = COLOR_NAVY
    run_ab_text = p_abs.add_run(
        "Most published breast-cancer risk models take a fixed table of patient features and return a single score. "
        "They usually do not record when each piece of patient information became available, or which data and model "
        "versions produced a given score. This paper describes OncoTwin-BRCA, an engineering prototype that addresses "
        "this gap for one task: estimating the five-year risk of recurrence after a primary breast-cancer diagnosis. "
        "The prototype stores each patient's clinical information as an append-only log of timestamped events modelled on "
        "HL7 FHIR R4 resources. The patient state is rebuilt from this log using a deterministic reducer, and it can also "
        "be reconstructed as it stood at any earlier clinical date or system time. Each risk estimate is linked atomically "
        "to the exact patient state, feature values, missing-value pattern, data version and model version that produced it, "
        "enabling end-to-end replay and verification. We report an empirical evaluation comparing calibrated logistic "
        "regression and gradient-boosted trees (XGBoost) with the Nottingham Prognostic Index (NPI) on the METABRIC "
        "cohort (N = 1,944), adhering to a preregistered analysis order on a frozen held-out test set (N = 389) with 2,000 "
        "bootstrap resamples. On the held-out test set, calibrated logistic regression achieved an AUROC of 0.723 "
        "(95% CI [0.662, 0.780]), calibrated XGBoost achieved 0.714 (95% CI [0.655, 0.770]), and the uncalibrated NPI "
        "achieved 0.720 (95% CI [0.660, 0.778]). The empirical finding indicates that learned tree boosting does not exceed "
        "standard clinical prognostic indexing on this clinical feature set. The contribution is an engineering design for "
        "traceable risk estimation, not a new clinical predictor. The system is a research prototype, not a medical device, "
        "and makes no treatment recommendations."
    )
    run_ab_text.font.size = Pt(9.5)

    p_idx = cell_abs.add_paragraph()
    p_idx.paragraph_format.space_before = Pt(4)
    p_idx.paragraph_format.space_after = Pt(0)
    run_idx_bold = p_idx.add_run("Index Terms—")
    run_idx_bold.font.bold = True
    run_idx_bold.font.size = Pt(9.0)
    run_idx_bold.font.color.rgb = COLOR_NAVY
    run_idx_text = p_idx.add_run(
        "breast cancer, calibration, digital twin, event sourcing, explainable machine learning, HL7 FHIR, provenance, METABRIC."
    )
    run_idx_text.font.size = Pt(9.0)
    run_idx_text.font.italic = True

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # Helper functions for headings
    def add_h1(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(16)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(13)
        r.font.bold = True
        r.font.color.rgb = COLOR_NAVY
        return p

    def add_h2(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(11)
        r.font.bold = True
        r.font.color.rgb = COLOR_STEEL
        return p

    def add_p(text):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.15
        r = p.add_run(text)
        r.font.name = "Calibri"
        r.font.size = Pt(10.0)
        return p

    # =========================================================================
    # SECTION I: INTRODUCTION
    # =========================================================================
    add_h1("I. INTRODUCTION")
    add_h2("A. Background and Motivation")
    add_p(
        "Breast cancer is a heterogeneous disease: patients with similar clinical findings can differ substantially "
        "in molecular subtype, response to therapy, and long-term recurrence outcome [1], [2]. Research consortia such "
        "as METABRIC [2] and The Cancer Genome Atlas (TCGA) [3] have provided deep multimodal insights into the genomic "
        "and clinical landscape of breast cancer. However, their public datasets are structured as static, cross-sectional "
        "tables with one row per patient."
    )
    add_p(
        "A clinical record, by contrast, is longitudinal. It evolves across clinics, biopsies, operative staging, pathology "
        "reviews, and surveillance visits. A risk estimate generated at a postoperative follow-up visit must depend strictly "
        "on what was clinically known at that visit. To support clinical safety and research integrity, two fundamental "
        "questions must be answerable for every estimate: what exact evidence was it based on, and which model version produced it?"
    )
    add_p(
        "The concept of a 'digital twin' is widely discussed in health technology. The National Academies of Sciences, "
        "Engineering, and Medicine define a digital twin as a virtual representation of a physical system that is dynamically "
        "updated with data from that system, has predictive capability, and informs decisions through two-way interaction [4]. "
        "In medicine, patient digital twins are envisioned as continually updated personal models [5]–[7]."
    )
    add_p(
        "OncoTwin-BRCA implements part of this vision. It maintains an individualized, versioned patient state rebuilt from "
        "an append-only event stream and delivers calibrated recurrence risk estimates. It does not send information back to change "
        "patient care, does not recommend therapies, and is not coupled to a live hospital EHR. For this reason, we describe "
        "OncoTwin-BRCA as an event-sourced patient-state prototype oriented toward digital twin architectures."
    )
    add_p(
        "Four technical and clinical challenges motivate this work:\n"
        "1. Persistent, Auditable State: Traditional risk calculators evaluate an isolated web form without storing the provenance of how findings accumulated or changed.\n"
        "2. Probability Calibration: A model can discriminate high-risk from low-risk patients (high AUROC) yet produce severely miscalibrated probabilities that mislead risk-benefit decisions [8], [9].\n"
        "3. Bounded Explanations: Feature attributions (such as SHAP) reflect mathematical model mechanics rather than clinical causality [10], [11], requiring explicit contextual safeguards.\n"
        "4. Software Traceability: Machine-learning systems suffer from hidden dependency drift and feedback loops [12]. While reporting standards such as TRIPOD+AI define study-level reporting requirements [13], they do not specify runtime mechanisms for individual prediction provenance."
    )

    add_h2("B. Contributions")
    add_p(
        "1. Formal Patient State as a Bitemporal Fold (C1): An event-sourced formalization where patient state is derived deterministically from an immutable event log using clinical effective time (t_eff) and system recorded time (t_rec), validated against four mathematical properties: determinism (R1), order independence (R2), idempotent ingestion (R3), and as-of temporal consistency (R4) (Sections III and IV-B).\n"
        "2. Strict Release Boundary (C2): Separation of state evolution from model releases. New clinical observations update patient state and risk estimates, but model weights remain strictly frozen until an offline, reviewed release gate is approved (Section IV-D).\n"
        "3. Traceable Provenance Record (C3): Atomic linkage of every prediction to state version, feature values, missingness mask, model artifact hash, calibrator, and explanation metadata, allowing bit-accurate re-execution audits (Section IV-F).\n"
        "4. Empirical METABRIC Evaluation (C4): Evaluation of calibrated logistic regression, uncalibrated XGBoost, calibrated XGBoost, and the Nottingham Prognostic Index (NPI) [14] on the METABRIC cohort adhering strictly to an anti-leakage, single test-set protocol with 2,000 bootstrap resamples (Sections V and VI)."
    )

    add_h2("C. Implementation Status (Table I)")
    add_p("Table I summarizes the real implementation status across the repository components and verified automated test suites.")

    # Table I
    t1_headers = ["Component", "Section", "Status", "Evidence Available in Repository"]
    t1_data = [
        ["Canonical event model and FHIR mapping", "IV-A", "Implemented", "data/src/fhir_adapter.py (8 LOINC codes, compound IHC, ordinal conversions); 111 tests passing."],
        ["Synthetic data generation or loading", "V-A", "Implemented", "data/samples/ (12 synthetic FHIR/clinical fixtures); data/src/etl.py (run_etl, compute_missingness); 33 tests."],
        ["PostgreSQL append-only event store", "IV-B", "Implemented", "backend/app/database.py, Alembic migrations (0001-0003), verified by scripts/verify_postgres.ps1."],
        ["Bitemporal reducer and as-of queries", "IV-B", "Implemented", "backend/app/store.py (rebuild_twin_state), backend/app/api.py temporal filters; verified by tests."],
        ["Property-based tests for R1-R4", "IV-B", "Implemented", "tests/test_properties.py (7 tests covering R1 determinism, R2 order independence, R3 idempotency, R4 as-of)."],
        ["Data-quality validation", "IV-C", "Implemented", "data/src/validation.py, data/src/etl.py (_validate_record), contracts/clinical-event.schema.json; 11 tests."],
        ["METABRIC loader and cohort replay", "IV-A, V-A", "Implemented", "ml/src/metabric_study.py (cBioPortal REST API extraction, cohort accounting, chronological replay)."],
        ["NPI computation", "III-E", "Implemented", "ml/src/metabric_study.py (Galea et al. 1992 formula and recalibrated logistic NPI)."],
        ["Logistic regression and XGBoost models", "IV-D", "Implemented", "ml/src/train.py, ml/src/metabric_study.py (tuned L2 LogisticRegression and XGBClassifier)."],
        ["Calibration (Platt scaling)", "IV-D", "Implemented", "ml/src/train.py, ml/src/metabric_study.py (Platt sigmoid via CalibratedClassifierCV on development folds)."],
        ["SHAP explanations", "IV-E", "Implemented", "ml/src/predict.py, ml/src/metabric_study.py (shap.TreeExplainer local attributions; Lundberg et al. 2020)."],
        ["Out-of-range and OOD flags", "IV-E", "Implemented", "ml/src/preprocess.py (ood_check), backend/app/api.py; verified by test suite in ml/tests/test_predict.py."],
        ["Model registry and release gate", "IV-D", "Implemented", "ml/models/model_metadata.json (SHA-256 artifact hashes, validation metrics, release metadata)."],
        ["Provenance record and replay audit", "IV-F", "Implemented", "contracts/audit-record.schema.json, backend/app/results.py; atomic prediction-audit linkage verified."],
        ["FastAPI backend", "IV-H", "Implemented", "backend/app/main.py, backend/app/api.py (REST endpoints for twins, events, projections, predictions, audits); 55 tests."],
        ["React dashboard", "IV-H", "Implemented", "frontend/src/App.tsx, frontend/src/api.ts (timeline, twin selector, SHAP bars, confidence pills); 34 Vitest tests."],
    ]
    t1_widths = [Inches(1.8), Inches(0.7), Inches(1.0), Inches(3.0)]
    t1 = doc.add_table(rows=len(t1_data) + 1, cols=4)
    format_table(t1, t1_widths, t1_headers, t1_data, alignments=["left", "center", "center", "left"])

    add_h2("D. Scope and Limitations")
    add_p(
        "The scope is strictly limited to estimating five-year recurrence risk after primary resection. The prototype "
        "does not perform diagnosis, recommend chemotherapy, select endocrine therapy, or estimate causal treatment effects. "
        "Prospective clinical testing and regulatory device clearance have not been conducted."
    )

    # =========================================================================
    # SECTION II: RELATED WORK
    # =========================================================================
    add_h1("II. RELATED WORK")
    add_h2("A. Digital Twins in Health and Oncology")
    add_p(
        "The digital-twin paradigm originates in aerospace engineering [15]. Its adoption in medicine ranges from organ-level "
        "biomechanical simulations to dynamic oncology models [5]–[7]. Laubenbacher et al. identify heterogeneous data integration, "
        "model governance, and patient privacy as major hurdles [7]. Asghar and Chung highlight the potential of combining molecular "
        "markers with personal patient timelines [1]. Venkatesh et al. emphasize regulatory transparency [6]. OncoTwin-BRCA "
        "operationalizes these principles through an append-only event log and explicit provenance records."
    )
    add_h2("B. Clinical Prognostic Indices and Multimodal Cohorts")
    add_p(
        "The Nottingham Prognostic Index (NPI) combines tumour diameter, histologic grade, and lymph node stage to stratify "
        "patients into prognostic groups [14]. Galea et al. established its utility for long-term survival, though not directly for "
        "five-year recurrence probabilities. PREDICT breast cancer models estimate treatment benefits [16] but require comprehensive "
        "therapy fields that public registries capture inconsistently."
    )
    add_p(
        "METABRIC characterized ~2,000 breast tumours with long-term follow-up [2], while TCGA-BRCA profiled comprehensive genomic "
        "layers across ~1,000 patients [3]. Both public resources, however, are released as static research matrices rather than event logs."
    )
    add_h2("C. Calibration of Clinical Predictions")
    add_p(
        "Calibration measures whether predicted risk probabilities match observed event rates [8], [9]. Modern neural networks and "
        "uncalibrated boosted trees often exhibit overconfidence or distortion [8], [9]. Platt scaling [18] fits a sigmoid transformation "
        "on held-out development splits to recalibrate probabilities. Steyerberg's framework [20] formalizes calibration slope (ideal 1.0) "
        "and intercept (ideal 0.0) as essential clinical quality measures alongside the Brier score [19]."
    )
    add_h2("D. Explainability and TreeSHAP")
    add_p(
        "Additive feature attributions such as SHAP allocate a prediction's deviation from base risk across input features [10]. "
        "Lundberg et al. (2020) developed TreeSHAP, an efficient exact polynomial-time algorithm for tree ensembles [32]. Rudin cautions "
        "that post-hoc explanations must not be conflated with transparent intrinsic models, and attributions must never be misinterpreted "
        "as causal treatment targets [11]."
    )

    # =========================================================================
    # SECTION III: PROBLEM FORMULATION
    # =========================================================================
    add_h1("III. PROBLEM FORMULATION")
    add_h2("A. Events and Event Identity")
    add_p(
        "Let P denote the set of patient identifiers. For patient p in P, E_p is a finite set of events: "
        "e = (id, p, type, t_eff, t_rec, src, payload, status, schema). The effective time t_eff records when the clinical "
        "observation occurred. The recorded time t_rec records when the event reached the system. Under Option B (source-derived "
        "identifier), event identity combines source identifiers with a cryptographic SHA-256 payload hash."
    )
    add_h2("B. State as a Bitemporal Fold")
    add_p(
        "Events are ordered by canonical sort key (t_eff, id), excluding t_rec to prevent arrival latency from distorting state order. "
        "For clinical query time tau_c and knowledge time tau_k, the visible event set is: "
        "E_p(tau_c, tau_k) = {e in E_p | t_eff(e) <= tau_c and t_rec(e) <= tau_k and not superseded(e)}. "
        "The patient state projection S_p(tau_c, tau_k) is computed as a fold over ordered events: "
        "S_p(tau_c, tau_k) = delta(...delta(delta(s_0, e_1), e_2)..., e_m)."
    )
    add_h2("C. Risk Estimate and NPI Comparator")
    add_p(
        "Given scoring model f_theta and Platt calibrator g, the calibrated recurrence risk is r_p = g(f_theta(x_p, m_p)) in [0, 1]. "
        "The Nottingham Prognostic Index is computed without fitting: NPI = 0.2 * tumour_size (cm) + node_stage + histologic_grade. "
        "To enable probabilistic calibration comparisons, a recalibrated NPI is fitted on the development set using univariable logistic regression: "
        "logit(p) = alpha + beta * NPI."
    )

    # =========================================================================
    # SECTION IV: SYSTEM DESIGN
    # =========================================================================
    add_h1("IV. SYSTEM DESIGN")
    add_h2("A. Canonical Event Model and FHIR R4 Adapter (Table II)")
    add_p("Table II details the mapping between canonical event schema fields and underlying FHIR R4 resource properties.")

    # Table II
    t2_headers = ["Canonical Field", "FHIR R4 Mapping", "System Role"]
    t2_data = [
        ["event_id", "Resource ID / UUID", "Unique event identifier with source provenance"],
        ["twin_id", "Patient.id", "Subject digital twin linkage"],
        ["event_type", "LOINC code / Category", "PATHOLOGY_RESULT, BIOMARKER_RESULT, DIAGNOSIS"],
        ["effective_time", "Observation.effectiveDateTime", "Clinical observation timestamp (t_eff)"],
        ["received_time", "Ingestion timestamp", "System knowledge timestamp (t_rec)"],
        ["status", "Observation.status", "final, amended, corrected"],
        ["payload", "Observation.value[x]", "Normalized clinical dictionary values (mm, grade 1-4)"],
        ["quality_status", "Validation result", "valid, warning, rejected"],
    ]
    t2_widths = [Inches(1.8), Inches(2.2), Inches(2.5)]
    t2 = doc.add_table(rows=len(t2_data) + 1, cols=3)
    format_table(t2, t2_widths, t2_headers, t2_data, alignments=["left", "left", "left"])

    add_h2("B. Provenance and Re-Execution Audit")
    add_p(
        "Every prediction stores an atomic AuditRecord containing: "
        "{audit_id, prediction_id, twin_id, snapshot_id, model_version, data_version, timestamp}. "
        "Re-execution audits verify that recomputing the prediction from stored inputs matches the original probability within "
        "10^-9 for logistic regression and 10^-6 for XGBoost."
    )

    # =========================================================================
    # SECTION V: DATA AND EVALUATION METHODOLOGY
    # =========================================================================
    add_h1("V. DATA AND EVALUATION METHODOLOGY")
    add_h2("A. Cohort Source: METABRIC")
    add_p(
        "METABRIC clinical data was obtained from cBioPortal (N = 2,509). The data dictionary was frozen with SHA-256 hash "
        "74a8167e40ec1e29b813e607cc4493170f37a5288d49c9ddce4c278f644ea269."
    )
    add_h2("B. Outcome and Censoring Definition")
    add_p(
        "The primary endpoint is relapse-free survival (RFS) within 60 months:\n"
        "- Recurrence (y = 1): RFS_STATUS is '1:Recurred' with RFS_MONTHS <= 60.0.\n"
        "- Recurrence-Free (y = 0): RFS_MONTHS >= 60.0.\n"
        "- Censored (< 60 months): Patients without recurrence whose follow-up terminated before 60 months (n = 195) or with missing follow-up (n = 129) are excluded from primary binary analysis.\n"
        "- Competing Risks: Patients who died of other causes before 60 months without recurrence (n = 80) are treated as censored at death in primary analysis. Sensitivity analysis uses Inverse Probability of Censoring Weighting (IPCW)."
    )
    add_h2("C. Cohort Accounting and Exclusions")
    add_p(
        "- Initial cBioPortal cohort: 2,509 patients.\n"
        "- Excluded due to censoring before 60 months: 195 patients.\n"
        "- Excluded due to missing follow-up: 129 patients.\n"
        "- Eligible labeled cohort: 2,193 patients (604 recurrences, 1,589 recurrence-free).\n"
        "- Complete NPI cohort: 1,944 patients (544 recurrences, 1,400 recurrence-free; event rate 27.98%)."
    )
    add_h2("D. Anti-Leakage Patient-Level Split")
    add_p(
        "The 1,944 complete patients are split strictly at the patient level:\n"
        "- Development Set (80%): 1,555 patients (435 recurrences).\n"
        "- Frozen Held-Out Test Set (20%): 389 patients (109 recurrences).\n"
        "Patient overlap between splits is strictly zero: dev intersect test is empty."
    )

    # =========================================================================
    # SECTION VI: EXPERIMENTAL RESULTS
    # =========================================================================
    add_h1("VI. EXPERIMENTAL RESULTS")
    add_h2("A. Test-Set Discrimination and Calibration (Table IV)")
    add_p(
        "Table IV presents the single final test-set run on 389 patients. All confidence intervals are derived from 2,000 "
        "patient-level bootstrap iterations following the analysis protocol in Section V-E."
    )

    # Table IV
    t4_headers = [
        "Model",
        "AUROC [95% CI]",
        "Brier [95% CI]",
        "ECE [95% CI]",
        "Cal. Slope [95% CI]",
        "Cal. Intercept [95% CI]",
    ]
    t4_data = [
        ["NPI score (raw, uncalibrated)", "0.720 [0.660, 0.778]", "n/a", "n/a", "n/a", "n/a"],
        ["NPI (recalibrated, fitted)", "0.720 [0.660, 0.778]", "0.177 [0.158, 0.197]", "0.043 [0.028, 0.089]", "1.117 [0.785, 1.492]", "0.077 [-0.292, 0.458]"],
        ["Logistic regression (calibrated)", "0.723 [0.662, 0.780]", "0.173 [0.154, 0.194]", "0.026 [0.025, 0.077]", "1.143 [0.818, 1.586]", "0.125 [-0.268, 0.589]"],
        ["XGBoost (uncalibrated)", "0.713 [0.655, 0.770]", "0.178 [0.158, 0.198]", "0.040 [0.027, 0.090]", "1.141 [0.802, 1.524]", "0.145 [-0.258, 0.587]"],
        ["XGBoost (calibrated)", "0.714 [0.655, 0.770]", "0.179 [0.158, 0.200]", "0.063 [0.040, 0.113]", "0.967 [0.674, 1.301]", "-0.033 [-0.409, 0.366]"],
    ]
    t4_widths = [Inches(1.8), Inches(1.1), Inches(0.9), Inches(0.9), Inches(0.9), Inches(0.9)]
    t4 = doc.add_table(rows=len(t4_data) + 1, cols=6)
    format_table(t4, t4_widths, t4_headers, t4_data, alignments=["left", "center", "center", "center", "center", "center"])

    add_h2("B. Hypotheses and Acceptance Criteria Evaluation")
    add_p(
        "- H1 (AUROC XGBoost >= Logistic): FAIL. Calibrated XGBoost achieved AUROC 0.714 vs 0.723 for calibrated Logistic Regression "
        "(difference: -0.0094, 95% CI [-0.0357, +0.0165]). The linear model slightly outperformed the tree ensemble.\n"
        "- H2 (Calibrated XGBoost ECE < 0.05): FAIL. Calibrated XGBoost had an ECE of 0.0629 (95% CI [0.040, 0.113]), exceeding the 0.05 threshold.\n"
        "- H3 (Calibration reduces XGBoost ECE): FAIL. Uncalibrated XGBoost had an ECE of 0.0397, whereas Platt sigmoid scaling yielded an ECE of 0.0629. "
        "While Platt scaling improved the calibration slope from 1.141 toward ideal 0.967 and the intercept from 0.145 to -0.033, it increased bin-level error by over-shrinking intermediate probabilities.\n"
        "- A1 (Simultaneous NPI Comparison): PASS. All four models and raw NPI were evaluated simultaneously on the identical 389 held-out test patients.\n"
        "- A2 (Property Tests R1-R4): PASS. All 7 automated property and adversarial test suites passed without failure.\n"
        "- A3 (Latency p95 < 500 ms): PASS. 95th-percentile response time was 16.50 ms under 1,000-request benchmark load."
    )

    add_h2("C. Software Verification and Property Tests (Table V)")
    add_p("Table V presents the software verification results, property-based tests, re-execution audit, and latency benchmarks.")

    # Table V
    t5_headers = ["Check", "Criterion", "Result", "Evidence / Details"]
    t5_data = [
        ["R1 Determinism", "Identical state hash across runs", "PASS", "100/100 repeated event log rebuilds yielded identical state (test_r1_determinism_property)."],
        ["R2 Order independence", "Identical state after permuting arrival order", "PASS", "50/50 randomized arrival permutations produced identical state (test_r2_order_independence_property)."],
        ["R3 Idempotency", "Duplicate delivery rejected without mutation", "PASS", "DuplicateEventError raised on re-ingestion; state unaltered."],
        ["R4 As-of consistency", "Later events do not alter earlier state", "PASS", "State at tau_c identical whether future events are present or absent."],
        ["Adversarial late amendments", "Earlier clinical finding arrives after later event", "PASS", "Canonical fold correctly applies late-arriving resection pathology."],
        ["Adversarial conflicts", "Identical timestamp contradictory labs", "PASS", "Deterministic event ID tie-breaker guarantees reproducible state."],
        ["Re-execution audit", "Prediction matches within tolerance", "PASS", "Max diff LR: 0.00 (< 10^-9), Max diff XGB: 0.00 (< 10^-6)."],
        ["A3 Latency, p95", "Below 500 ms under stated load", "PASS", "p50 = 12.25 ms, p95 = 16.50 ms, p99 = 19.39 ms (1,000 runs, x86-64)."],
    ]
    t5_widths = [Inches(1.8), Inches(1.8), Inches(0.8), Inches(2.1)]
    t5 = doc.add_table(rows=len(t5_data) + 1, cols=4)
    format_table(t5, t5_widths, t5_headers, t5_data, alignments=["left", "left", "center", "left"])

    add_h2("D. Graphical Results: Calibration, Decision Curve, and TreeSHAP")
    add_p(
        "Figure 1 displays the test-set calibration curves. Figure 2 illustrates the decision curve analysis demonstrating net benefit "
        "across clinical risk thresholds. Figure 3 presents the TreeSHAP summary plot illustrating feature attributions on XGBoost log-odds margins."
    )

    # Embed Figures
    fig_cal = FIGURES_DIR / "fig_calibration.png"
    if fig_cal.exists():
        add_figure_with_caption(
            doc,
            fig_cal,
            "Fig. 1. Calibration curves on the frozen METABRIC test set (N = 389) across 10 probability bins. Logistic regression (calibrated, ECE = 0.026) closely tracks the ideal diagonal.",
            width=Inches(5.5),
        )

    fig_dca = FIGURES_DIR / "fig_decision_curve.png"
    if fig_dca.exists():
        add_figure_with_caption(
            doc,
            fig_dca,
            "Fig. 2. Decision Curve Analysis (DCA) comparing net benefit across threshold probabilities between 5% and 50%.",
            width=Inches(5.5),
        )

    fig_shap = FIGURES_DIR / "fig_shap.png"
    if fig_shap.exists():
        add_figure_with_caption(
            doc,
            fig_shap,
            "Fig. 3. TreeSHAP feature attributions on XGBoost log-odds margins for the 389 held-out test patients. Red indicates high feature values.",
            width=Inches(5.5),
        )

    add_h2("E. Subgroup and Sensitivity Analysis")
    add_p(
        "- Subgroup Discrimination: In ER-negative patients (n = 97), discrimination was highest (XGBoost AUROC 0.771, Logistic 0.765, NPI 0.772). "
        "In ER-positive patients (n = 289), discrimination was lower (XGBoost 0.665, Logistic 0.684, NPI 0.670). "
        "Patients over 65 (n = 155) exhibited high discrimination across all models (NPI 0.824, Logistic 0.796, XGBoost 0.767).\n"
        "- IPCW Sensitivity Analysis: Weighting test patients by the inverse probability of remaining uncensored at 60 months yielded a Brier score of "
        "0.1787 for calibrated XGBoost (vs 0.1788 unweighted) and 0.1730 for calibrated Logistic Regression (vs 0.1735 unweighted). "
        "The difference (< 0.0005) confirms that censoring exclusion did not induce significant selection bias."
    )

    add_h2("F. External Validation Feasibility on TCGA-BRCA")
    add_p(
        "External validation on TCGA-BRCA was evaluated and determined to be infeasible:\n"
        "1. Follow-up Truncation: Median disease-free follow-up in TCGA-BRCA is only 25.0 months. 677 of 941 patients (71.9%) with DFS data "
        "are censored prior to 60 months without recurrence. Only 74 recurrences and 190 recurrence-free patients reached 60 months.\n"
        "2. Feature Incompatibility: TCGA clinical matrices record pathologic T stage (T1-T4) rather than continuous tumour diameter (mm), "
        "and histologic grade is absent for the vast majority of patients. Direct evaluation without non-standard imputation would introduce severe bias."
    )

    # =========================================================================
    # SECTION VII & VIII: DISCUSSION AND CONCLUSION
    # =========================================================================
    add_h1("VII. DISCUSSION AND LIMITATIONS")
    add_h2("A. Clinical Implications of the Empirical Finding")
    add_p(
        "The empirical results reveal that neither calibrated logistic regression (AUROC 0.723) nor XGBoost (AUROC 0.714) provided a "
        "clinically meaningful improvement over the simple, uncalibrated NPI score (AUROC 0.720) on this standard clinical feature set. "
        "The Nottingham Prognostic Index, established over three decades ago by Galea et al. [14], captures the predominant prognostic "
        "variance contained in tumour size, nodal involvement, and grade. Adding age and receptor status via nonlinear gradient boosting "
        "offered no discrimination benefit. This negative finding is methodologically important: it demonstrates that algorithmic complexity "
        "cannot compensate for the absence of molecular or genomic markers."
    )
    add_h2("B. Traceability and Digital Twin Verification")
    add_p(
        "The primary contribution of OncoTwin-BRCA lies in system architecture. By decoupling clinical effective time from system ingestion "
        "time and enforcing an immutable event log, the system guarantees verifiable provenance. Re-execution audits reproduced predictions "
        "bit-for-bit, while p95 response times remained below 20 ms."
    )
    add_h2("C. Limitations")
    add_p(
        "1. Retrospective Cohort: METABRIC is retrospective, derived from multiple centers spanning 1977-2005 with variable historic systemic therapy protocols.\n"
        "2. Absence of Genomic Signatures: Multi-gene signatures (such as Oncotype DX or MammaPrint) were not available for integration into the feature vector.\n"
        "3. Synthetic Event Replay: Because METABRIC is structured as a cross-sectional table, event timestamps were assigned using clinical staging "
        "sequence offsets (biopsy -> pathology -> biomarkers -> surveillance). Prospective clinical validation on true longitudinal EHR streams is required."
    )

    add_h1("VIII. CONCLUSION")
    add_p(
        "OncoTwin-BRCA demonstrates an event-sourced architecture for traceable breast-cancer recurrence risk prediction. The empirical evaluation "
        "on METABRIC highlights that complex tree-boosting models perform comparably to the established NPI on routine clinical variables, "
        "emphasizing the importance of calibration, auditability, and restrained claims in digital health engineering."
    )

    # =========================================================================
    # REFERENCES
    # =========================================================================
    add_h1("REFERENCES")
    refs = [
        "[1] A. Asghar and C. Chung, 'Application of digital twins for personalized oncology,' Nature Reviews Cancer, vol. 25, no. 11, pp. 823-825, 2025.",
        "[2] C. Curtis, S. P. Shah, S.-F. Chin et al., 'The genomic and transcriptomic architecture of 2,000 breast tumours reveals novel subgroups,' Nature, vol. 486, pp. 346-352, 2012.",
        "[3] The Cancer Genome Atlas Network, 'Comprehensive molecular portraits of human breast tumours,' Nature, vol. 490, pp. 61-70, 2012.",
        "[4] National Academies of Sciences, Engineering, and Medicine, Foundational Research Gaps and Future Directions for Digital Twins. Washington, DC: National Academies Press, 2024.",
        "[5] E. Katsoulakis, Q. Wang, H. Wu et al., 'Digital twins for health: A scoping review,' npj Digital Medicine, vol. 7, p. 77, 2024.",
        "[6] K. P. Venkatesh, M. M. Raza, and J. C. Kvedar, 'Health digital twins as tools for precision medicine: Considerations for computation, implementation, and regulation,' npj Digital Medicine, vol. 5, p. 150, 2022.",
        "[7] R. Laubenbacher, B. Mehrad, I. Shmulevich, and N. Trayanova, 'Digital twins in medicine,' Nature Computational Science, vol. 4, pp. 184-191, 2024.",
        "[8] A. Niculescu-Mizil and R. Caruana, 'Predicting good probabilities with supervised learning,' in Proc. 22nd Int. Conf. Machine Learning (ICML), 2005, pp. 625-632.",
        "[9] C. Guo, G. Pleiss, Y. Sun, and K. Q. Weinberger, 'On calibration of modern neural networks,' in Proc. 34th Int. Conf. Machine Learning (ICML), vol. 70, 2017, pp. 1321-1330.",
        "[10] S. M. Lundberg and S.-I. Lee, 'A unified approach to interpreting model predictions,' in Advances in Neural Information Processing Systems, vol. 30, 2017, pp. 4765-4774.",
        "[11] C. Rudin, 'Stop explaining black box machine learning models for high stakes decisions and use interpretable models instead,' Nature Machine Intelligence, vol. 1, pp. 206-215, 2019.",
        "[12] D. Sculley et al., 'Hidden technical debt in machine learning systems,' in Advances in Neural Information Processing Systems, vol. 28, 2015, pp. 2503-2511.",
        "[13] G. S. Collins et al., 'TRIPOD+AI statement: Updated guidance for reporting clinical prediction models that use regression or machine learning methods,' BMJ, vol. 385, e078378, 2024.",
        "[14] M. H. Galea, R. W. Blamey, C. E. Elston, and I. O. Ellis, 'The Nottingham Prognostic Index in primary breast cancer,' Breast Cancer Research and Treatment, vol. 22, no. 3, pp. 207-219, 1992.",
        "[15] M. Grieves and J. Vickers, 'Digital twin: Mitigating unpredictable, undesirable emergent behavior in complex systems,' in Transdisciplinary Perspectives on Complex Systems. Springer, 2017, pp. 85-113.",
        "[16] F. J. Candido dos Reis et al., 'An updated PREDICT breast cancer prognostication and treatment benefit prediction model with independent validation,' Breast Cancer Research, vol. 19, p. 58, 2017.",
        "[17] S. Paik et al., 'A multigene assay to predict recurrence of tamoxifen-treated, node-negative breast cancer,' New England Journal of Medicine, vol. 351, no. 27, pp. 2817-2826, 2004.",
        "[18] J. C. Platt, 'Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods,' in Advances in Large Margin Classifiers. MIT Press, 1999, pp. 61-74.",
        "[19] G. W. Brier, 'Verification of forecasts expressed in terms of probability,' Monthly Weather Review, vol. 78, no. 1, pp. 1-3, 1950.",
        "[20] E. W. Steyerberg, Clinical Prediction Models: A Practical Approach to Development, Validation, and Updating, 2nd ed. Springer, 2019.",
        "[21] S. M. Lundberg et al., 'From local explanations to global understanding with explainable AI for trees,' Nature Machine Intelligence, vol. 2, no. 1, pp. 56-67, 2020.",
        "[22] M. T. Ribeiro, S. Singh, and C. Guestrin, ''Why should I trust you?': Explaining the predictions of any classifier,' in Proc. 22nd ACM SIGKDD, 2016, pp. 1135-1144.",
        "[23] Health Level Seven International, 'HL7 FHIR Release 4 (v4.0.1),' 2026. [Online]. Available: https://hl7.org/fhir/R4/",
        "[24] J. Walonoski et al., 'Synthea: An approach, method, and software mechanism for generating synthetic patients and the synthetic electronic health record,' JAMIA, vol. 25, no. 3, pp. 230-238, 2018.",
        "[25] M. Fowler, 'Event sourcing,' martinfowler.com, 2005. [Online]. Available: https://martinfowler.com/eaaDev/EventSourcing.html",
        "[26] L. Lamport, 'Time, clocks, and the ordering of events in a distributed system,' Communications of the ACM, vol. 21, no. 7, pp. 558-565, 1978.",
        "[27] M. Kleppmann, Designing Data-Intensive Applications. O'Reilly Media, 2017.",
        "[28] M. D. Wilkinson et al., 'The FAIR Guiding Principles for scientific data management and stewardship,' Scientific Data, vol. 3, p. 160018, 2016.",
        "[29] T. Chen and C. Guestrin, 'XGBoost: A scalable tree boosting system,' in Proc. 22nd ACM SIGKDD, 2016, pp. 785-794.",
        "[30] National Cancer Institute, 'The Cancer Genome Atlas Program: TCGA-BRCA,' 2024. [Online]. Available: https://www.cancer.gov/tcga",
        "[31] A. J. Vickers and E. B. Elkin, 'Decision curve analysis: A novel method for evaluating prediction models,' Medical Decision Making, vol. 26, no. 6, pp. 565-574, 2006.",
        "[32] S. M. Lundberg et al., 'From local explanations to global understanding with explainable AI for trees,' Nature Machine Intelligence, vol. 2, no. 1, pp. 56-67, 2020.",
        "[33] K. Clark et al., 'The Cancer Imaging Archive (TCIA): Maintaining and operating a public information repository,' Journal of Digital Imaging, vol. 26, pp. 1045-1057, 2013.",
    ]
    for r in refs:
        p_ref = doc.add_paragraph()
        p_ref.paragraph_format.space_before = Pt(0)
        p_ref.paragraph_format.space_after = Pt(3)
        p_ref.paragraph_format.left_indent = Inches(0.25)
        p_ref.paragraph_format.first_line_indent = Inches(-0.25)
        run_ref = p_ref.add_run(r)
        run_ref.font.name = "Calibri"
        run_ref.font.size = Pt(8.5)
        run_ref.font.color.rgb = COLOR_DARK

    # Save to documents directory
    doc.save(str(OUTPUT_DOCX))
    print(f"Saved Word document to: {OUTPUT_DOCX}")

    # Also save copy to root and DataSet directory
    import shutil
    shutil.copy(OUTPUT_DOCX, ROOT / "OncoTwin_BRCA_paper.docx")
    shutil.copy(OUTPUT_DOCX, DATASET_DOCX)
    print(f"Mirrored Word document to: {ROOT / 'OncoTwin_BRCA_paper.docx'}")
    print(f"Mirrored Word document to: {DATASET_DOCX}")


if __name__ == "__main__":
    build_word_document()
