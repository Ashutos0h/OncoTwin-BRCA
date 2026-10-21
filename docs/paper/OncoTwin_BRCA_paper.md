# OncoTwin-BRCA: An Event-Sourced Patient-State Prototype for Traceable Breast-Cancer Recurrence Risk Estimation

**Ashutosh Verma, Shivansh Vats, Rajat Bhardwaj, and Bhumika Upreti**  
*Department of Computer Science & Engineering (Artificial Intelligence), ABES Institute of Technology, Ghaziabad, Uttar Pradesh, India*  
Corresponding author e-mail: vashutosh685@gmail.com  
Supervisor: Dr. Vineet Kumar Singh, Department of Computer Science & Engineering (AI), ABES Institute of Technology  

---

### Abstract
Most published breast-cancer risk models take a fixed table of patient features and return a single score. They usually do not record when each piece of patient information became available, or which data and model versions produced a given score. This paper describes **OncoTwin-BRCA**, an engineering prototype that addresses this gap for one task: estimating the five-year risk of recurrence after a primary breast-cancer diagnosis. The prototype stores each patient's clinical information as an append-only log of timestamped events modelled on HL7 FHIR R4 resources. The patient state is rebuilt from this log using a deterministic reducer, and it can also be reconstructed as it stood at any earlier clinical date or system time. Each risk estimate is linked atomically to the exact patient state, feature values, missing-value pattern, data version and model version that produced it, enabling end-to-end replay and verification. We report an empirical evaluation comparing calibrated logistic regression and gradient-boosted trees (XGBoost) with the Nottingham Prognostic Index (NPI) on the METABRIC cohort ($N=1{,}944$), adhering to a preregistered analysis order on a frozen held-out test set ($N=389$) with 2,000 bootstrap resamples. On the held-out test set, calibrated logistic regression achieved an AUROC of 0.723 (95% CI [0.662, 0.780]), calibrated XGBoost achieved 0.714 (95% CI [0.655, 0.770]), and the uncalibrated NPI achieved 0.720 (95% CI [0.660, 0.778]). The empirical finding indicates that learned tree boosting does not exceed standard clinical prognostic indexing on this clinical feature set. The contribution is an engineering design for traceable risk estimation, not a new clinical predictor. The system is a research prototype, not a medical device, and makes no treatment recommendations.

**Index Terms:** breast cancer, calibration, digital twin, event sourcing, explainable machine learning, HL7 FHIR, provenance, METABRIC.

---

## I. INTRODUCTION

### A. Background and Motivation
Breast cancer is a heterogeneous disease: patients with similar clinical findings can differ substantially in molecular subtype, response to therapy, and long-term recurrence outcome [1], [2]. Research consortia such as METABRIC [2] and The Cancer Genome Atlas (TCGA) [3] have provided deep multimodal insights into the genomic and clinical landscape of breast cancer. However, their public datasets are structured as static, cross-sectional tables with one row per patient.

A clinical record, by contrast, is longitudinal. It evolves across clinics, biopsies, operative staging, pathology reviews, and surveillance visits. A risk estimate generated at a postoperative follow-up visit must depend strictly on what was clinically known at that visit. To support clinical safety and research integrity, two fundamental questions must be answerable for every estimate: *what exact evidence was it based on*, and *which model version produced it*?

The concept of a "digital twin" is widely discussed in health technology. The National Academies of Sciences, Engineering, and Medicine define a digital twin as a virtual representation of a physical system that is dynamically updated with data from that system, has predictive capability, and informs decisions through two-way interaction [4]. In medicine, patient digital twins are envisioned as continually updated personal models [5]–[7].

OncoTwin-BRCA implements part of this vision. It maintains an individualized, versioned patient state rebuilt from an append-only event stream and delivers calibrated recurrence risk estimates. It does not send information back to change patient care, does not recommend therapies, and is not coupled to a live hospital EHR. For this reason, we describe OncoTwin-BRCA as an *event-sourced patient-state prototype* oriented toward digital twin architectures.

Three technical and clinical challenges motivate this work:
1. **Persistent, Auditable State:** Traditional risk calculators evaluate an isolated web form without storing the provenance of how findings accumulated or changed.
2. **Probability Calibration:** A model can discriminate high-risk from low-risk patients (high AUROC) yet produce severely miscalibrated probabilities that mislead risk-benefit decisions [8], [9].
3. **Bounded Explanations:** Feature attributions (such as SHAP) reflect model mechanics rather than clinical causality [10], [11], requiring explicit contextual safeguards.
4. **Software Traceability:** Machine-learning systems suffer from hidden dependency drift and feedback loops [12]. While reporting standards such as TRIPOD+AI define study-level reporting requirements [13], they do not specify runtime mechanisms for individual prediction provenance.

### B. Contributions
1. **Formal Patient State as a Bitemporal Fold (C1):** An event-sourced formalization where patient state is derived deterministically from an immutable event log using clinical effective time ($t_{\text{eff}}$) and system recorded time ($t_{\text{rec}}$), validated against four mathematical properties: determinism (R1), order independence (R2), idempotent ingestion (R3), and as-of temporal consistency (R4) (Sections III and IV-B).
2. **Strict Release Boundary (C2):** Separation of state evolution from model releases. New clinical observations update patient state and risk estimates, but model weights remain strictly frozen until an offline, reviewed release gate is approved (Section IV-D).
3. **Traceable Provenance Record (C3):** Atomic linkage of every prediction to state version, feature values, missingness mask, model artifact hash, calibrator, and explanation metadata, allowing bit-accurate re-execution audits (Section IV-F).
4. **Empirical METABRIC Evaluation (C4):** Evaluation of calibrated logistic regression, uncalibrated XGBoost, calibrated XGBoost, and the Nottingham Prognostic Index (NPI) [14] on the METABRIC cohort adhering strictly to an anti-leakage, single test-set protocol with 2,000 bootstrap resamples (Sections V and VI).

### C. Implementation Status
Table I summarizes the real implementation status across the repository.

#### TABLE I: Implementation Status of System Components
| Component | Section | Status | Evidence Available in Repository |
| :--- | :--- | :--- | :--- |
| **Canonical event model and FHIR mapping** | IV-A | **Implemented** | `data/src/fhir_adapter.py` (8 LOINC codes, compound IHC, ordinal conversions); 61 unit tests passing in `data/tests/test_fhir_adapter.py`. |
| **Synthetic data generation or loading** | V-A | **Implemented** | `data/samples/` (11 synthetic FHIR/clinical fixtures); `data/src/etl.py` (`run_etl`, `compute_missingness`); 33 unit tests in `data/tests/test_etl.py`. |
| **PostgreSQL append-only event store** | IV-B | **Implemented** | `backend/app/database.py`, Alembic migrations in `backend/alembic/`, `infra/docker-compose.yml`, verified by `scripts/verify_postgres.ps1`. |
| **Bitemporal reducer and as-of queries** | IV-B | **Implemented** | `backend/app/store.py` (`rebuild_twin_state`), `backend/app/api.py` temporal filters; verified by `backend/tests/test_store.py`. |
| **Property-based tests for R1–R4** | IV-B | **Implemented** | `tests/test_properties.py` (7 tests covering R1 determinism, R2 50-permutation order independence, R3 idempotency, R4 as-of consistency, late amendments, conflict tie-breaking). |
| **Data-quality validation** | IV-C | **Implemented** | `data/src/validation.py`, `data/src/etl.py` (`_validate_record`), `contracts/clinical-event.schema.json`; 11 tests in `data/tests/test_validation.py`. |
| **METABRIC loader and cohort replay** | IV-A, V-A | **Implemented** | `ml/src/metabric_study.py` (cBioPortal REST API extraction, cohort accounting, chronological replay pipeline); cached in `data/raw/`. |
| **NPI computation** | III-E | **Implemented** | `ml/src/metabric_study.py` (Galea et al. 1992 formula and recalibrated logistic NPI). |
| **Logistic regression and XGBoost models** | IV-D | **Implemented** | `ml/src/train.py`, `ml/src/metabric_study.py` (tuned L2 LogisticRegression and XGBClassifier); serialized in `ml/models/`. |
| **Calibration (Platt scaling)** | IV-D | **Implemented** | `ml/src/train.py`, `ml/src/metabric_study.py` (Platt sigmoid via `CalibratedClassifierCV` on held-out development folds). |
| **SHAP explanations** | IV-E | **Implemented** | `ml/src/predict.py`, `ml/src/metabric_study.py` (`shap.TreeExplainer` local attributions on log-odds margins; Lundberg et al. 2020). |
| **Out-of-range and OOD flags** | IV-E | **Implemented** | `ml/src/preprocess.py` (`ood_check`), `backend/app/api.py`; verified by test suite in `ml/tests/test_predict.py`. |
| **Model registry and release gate** | IV-D | **Implemented** | `ml/models/model_metadata.json` (SHA-256 artifact hashes, validation metrics, release metadata); `backend/app/config.py` inference toggle. |
| **Provenance record and replay audit** | IV-F | **Implemented** | `contracts/audit-record.schema.json`, `backend/app/results.py`; atomic prediction-audit linkage verified in `backend/tests/test_results.py`. |
| **FastAPI backend** | IV-H | **Implemented** | `backend/app/main.py`, `backend/app/api.py` (REST endpoints for twins, events, projections, predictions, audits, model info); 23 tests in `backend/tests/test_api.py`. |
| **React dashboard** | IV-H | **Implemented** | `frontend/src/App.tsx`, `frontend/src/api.ts` (timeline, twin selector, SHAP feature bars, confidence pills, audit inspector); 34 Vitest tests passing. |

### D. Scope and Limitations
The scope is strictly limited to estimating five-year recurrence risk after primary resection. The prototype does not perform diagnosis, recommend chemotherapy, select endocrine therapy, or estimate causal treatment effects. Prospective clinical testing and regulatory device clearance have not been conducted.

---

## II. RELATED WORK

### A. Digital Twins in Health and Oncology
The digital-twin paradigm originates in aerospace engineering [15]. Its adoption in medicine ranges from organ-level biomechanical simulations to dynamic oncology models [5]–[7]. Laubenbacher et al. identify heterogeneous data integration, model governance, and patient privacy as major hurdles [7]. Asghar and Chung highlight the potential of combining molecular markers with personal patient timelines [1]. Venkatesh et al. emphasize regulatory transparency [6]. OncoTwin-BRCA operationalizes these principles through an append-only event log and explicit provenance records.

### B. Clinical Prognostic Indices and Multimodal Cohorts
The Nottingham Prognostic Index (NPI) combines tumour diameter, histologic grade, and lymph node stage to stratify patients into prognostic groups [14]. Galea et al. established its utility for long-term survival, though not directly for five-year recurrence probabilities. PREDICT breast cancer models estimate treatment benefits [16] but require comprehensive therapy fields that public registries capture inconsistently.

METABRIC characterized ~2,000 breast tumours with long-term follow-up [2], while TCGA-BRCA profiled comprehensive genomic layers across ~1,000 patients [3]. Both public resources, however, are released as static research matrices rather than event logs.

### C. Calibration of Clinical Predictions
Calibration measures whether predicted risk probabilities match observed event rates [8], [9]. Modern neural networks and uncalibrated boosted trees often exhibit overconfidence or distortion [8], [9]. Platt scaling [18] fits a sigmoid transformation on held-out development splits to recalibrate probabilities. Steyerberg's framework [20] formalizes calibration slope (ideal 1.0) and intercept (ideal 0.0) as essential clinical quality measures alongside the Brier score [19].

### D. Explainability and TreeSHAP
Additive feature attributions such as SHAP allocate a prediction's deviation from base risk across input features [10]. Lundberg et al. (2020) developed TreeSHAP, an efficient exact polynomial-time algorithm for tree ensembles [32]. Rudin cautions that post-hoc explanations must not be conflated with transparent intrinsic models, and attributions must never be misinterpreted as causal treatment targets [11].

---

## III. PROBLEM FORMULATION

### A. Events
Let $\mathcal{P}$ denote the set of patient identifiers. For patient $p \in \mathcal{P}$, $E_p$ is a finite set of events:
$$e = (\text{id}, p, \text{type}, t_{\text{eff}}, t_{\text{rec}}, \text{src}, \text{payload}, \text{status}, \text{schema})$$
The effective time $t_{\text{eff}}$ records when the clinical observation occurred. The recorded time $t_{\text{rec}}$ records when the event reached the system.

### B. Event Identity
Under Option B (source-derived identifier), the event identifier $\text{id}$ is assigned from the source system resource, accompanied by a cryptographic SHA-256 payload hash (`content_hash`). Repeated arrivals of identical payloads are handled idempotently; conflicting payloads reusing an existing identifier are flagged and isolated.

### C. State as a Bitemporal Fold
Events are ordered by canonical sort key $(t_{\text{eff}}, \text{id})$, excluding $t_{\text{rec}}$ to prevent arrival latency from distorting state order. For clinical query time $\tau_c$ and knowledge time $\tau_k$, the visible event set is:
$$E_p(\tau_c, \tau_k) = \{e \in E_p \mid t_{\text{eff}}(e) \le \tau_c \land t_{\text{rec}}(e) \le \tau_k \land \neg \text{superseded}(e)\}$$
The patient state projection $S_p(\tau_c, \tau_k)$ is computed as a fold over ordered events $e_1, \dots, e_m$:
$$S_p(\tau_c, \tau_k) = \delta(\dots \delta(\delta(s_0, e_1), e_2)\dots, e_m) \tag{1}$$

### D. Feature Snapshot and Missingness
A deterministic feature mapping $\phi$ extracts feature vector $x_p$ and missingness mask $m_p$:
$$x_p = \phi(S_p(\tau_c, \tau_k)) \in (\mathbb{R} \cup \{\text{NaN}\})^d, \quad m_p \in \{0, 1\}^d \tag{2}$$
Missing fields are never silently fabricated; the missingness mask $m_p$ is preserved in the snapshot and recorded in the audit trail.

### E. Risk Estimate and NPI Comparator
Given scoring model $f_\theta$ and Platt calibrator $g$:
$$r_p(\tau_c, \tau_k) = g(f_\theta(x_p, m_p)) \in [0, 1] \tag{3}$$
The Nottingham Prognostic Index is computed without fitting:
$$\text{NPI} = 0.2 \times \text{tumour size (cm)} + \text{node stage} + \text{histologic grade} \tag{4}$$
where node stage is 1 (0 positive nodes), 2 (1–3 positive nodes), or 3 ($\ge 4$ positive nodes). To enable probabilistic calibration comparisons, a *recalibrated NPI* is fitted on the development set using one-variable logistic regression: $\text{logit}(p) = \alpha + \beta \cdot \text{NPI}$.

### F. System Requirements
- **R1 Determinism:** Identical events processed by the same reducer version always yield identical state and hash.
- **R2 Order Independence:** Ingestion order permutations produce identical states.
- **R3 Idempotency:** Duplicate ingestion produces no state changes.
- **R4 As-of Consistency:** States as of $(\tau_c, \tau_k)$ depend strictly on events visible at that boundary.
- **R5 Calibrated Output:** Output probabilities are calibrated and evaluated on held-out test data.
- **R6 Bounded Explanation:** Attributions are explicitly labeled as model behavior, not clinical causality.
- **R7 Provenance Completeness:** Every prediction traces to snapshot hash, model hash, and data version.
- **R8 Controlled Model Change:** Patient updates cannot trigger background retraining.

---

## IV. SYSTEM DESIGN

The architecture comprises five modular layers: Ingestion, State Store & Reducer, Prediction & Calibration, Explanation, and User Dashboard.

### A. Canonical Event Model and FHIR R4 Adapter
Source records are converted to `ClinicalEvent` instances matching `contracts/clinical-event.schema.json`. Table II details the mapping.

#### TABLE II: Canonical Event Fields and FHIR R4 Origin
| Canonical Field | FHIR R4 Mapping | System Role |
| :--- | :--- | :--- |
| `event_id` | Resource ID / UUID | Unique event identifier |
| `twin_id` | `Patient.id` | Subject digital twin linkage |
| `event_type` | LOINC code / Category | `PATHOLOGY_RESULT`, `BIOMARKER_RESULT`, `DIAGNOSIS` |
| `effective_time` | `Observation.effectiveDateTime` | Clinical observation timestamp ($t_{\text{eff}}$) |
| `received_time` | Ingestion timestamp | System knowledge timestamp ($t_{\text{rec}}$) |
| `status` | `Observation.status` | `final`, `amended`, `corrected` |
| `payload` | `Observation.value[x]` | Normalized clinical dictionary dictionary values |
| `quality_status`| Validation result | `valid`, `warning`, `rejected` |

### B. Event Store, Reducer, and As-Of Queries
The storage engine uses PostgreSQL with an append-only table. Rebuilding folds events in canonical sequence $(t_{\text{eff}}, \text{id})$. Projections are hashed and checked against the ordered event stream. Property-based tests verify R1–R4 across synthetic perturbations.

### C. Feature Snapshot & Validation
Validation rejects out-of-range numeric values and malformed categoricals prior to snapshot generation. The resulting feature vector and missingness mask are hashed with SHA-256.

### D. Model Comparison, Calibration & Release Gate
Two candidate classifiers are trained on the development split:
1. L2-regularized Logistic Regression with median imputation and standardization.
2. Gradient Boosted Trees (XGBoost) with native missingness handling.

Both are calibrated with Platt scaling fitted on development cross-validation folds. A model registry enforces an offline release gate: only models with verified validation metrics and registered artifact hashes are deployable.

### E. TreeSHAP Explanations
TreeSHAP [32] computes exact Shapley attributions on XGBoost log-odds margins. The user dashboard displays attributions with an explicit notice: *SHAP values explain mathematical model behavior across features, not biological causality.* Out-of-distribution (OOD) checks flag values beyond training boundaries ($\text{tumour size} > 100\text{ mm}$, $\text{positive nodes} > 30$, $\text{grade} \notin \{1,2,3\}$).

### F. Provenance and Re-Execution Audit
Every prediction stores an atomic `AuditRecord` containing:
$$\{\text{audit\_id}, \text{prediction\_id}, \text{twin\_id}, \text{snapshot\_id}, \text{model\_version}, \text{data\_version}, \text{timestamp}\}$$
Re-execution verifies that recomputing the prediction from stored inputs matches the original probability within $10^{-9}$ for logistic regression and $10^{-6}$ for XGBoost.

---

## V. DATA AND EVALUATION METHODOLOGY

### A. Cohort Source: METABRIC
METABRIC clinical data was obtained from cBioPortal ($N=2{,}509$). The data dictionary was frozen with SHA-256 hash `74a8167e40ec1e29b813e607cc4493170f37a5288d49c9ddce4c278f644ea269`.

### B. Outcome and Censoring Definition
The primary endpoint is relapse-free survival (RFS) within 60 months. 
- **Recurrence ($\mathbf{y=1}$):** `RFS_STATUS` is "1:Recurred" with `RFS_MONTHS` $\le 60.0$.
- **Recurrence-Free ($\mathbf{y=0}$):** `RFS_MONTHS` $\ge 60.0$.
- **Censored (< 60 months):** Patients without recurrence whose follow-up terminated before 60 months ($n=195$) or with missing follow-up ($n=129$) are excluded from primary binary analysis.
- **Competing Risks:** Patients who died of other causes before 60 months without recurrence ($n=80$) are treated as censored at death in primary analysis. Sensitivity analysis uses Inverse Probability of Censoring Weighting (IPCW).

### C. Cohort Accounting and Exclusions
- Initial cBioPortal cohort: **2,509** patients.
- Excluded due to censoring before 60 months: **195** patients.
- Excluded due to missing follow-up: **129** patients.
- Eligible labeled cohort: **2,193** patients (604 recurrences, 1,589 recurrence-free).
- Complete NPI cohort: **1,944** patients (544 recurrences, 1,400 recurrence-free; event rate 27.98%).

### D. Anti-Leakage Patient-Level Split
The 1,944 complete patients are split into:
- **Development Set (80%):** 1,555 patients (435 recurrences).
- **Frozen Held-Out Test Set (20%):** 389 patients (109 recurrences).
Patient overlap between splits is strictly zero: $\text{dev} \cap \text{test} = \emptyset$.

### E. Analysis Protocol
The analysis strictly followed Section V-E:
1. Freeze data dictionary and record hash.
2. Develop models and fit Platt calibrator on development set only using 5-fold cross-validation.
3. Register models and lock parameters.
4. Score the frozen held-out test set **once**.
5. Compute metrics with 2,000 bootstrap resamples, decision curves, TreeSHAP, and subgroup analyses.

---

## VI. EXPERIMENTAL RESULTS

### A. Test-Set Discrimination and Calibration (Table IV)
Table IV presents the single final test-set run on 389 patients. All confidence intervals are derived from 2,000 patient-level bootstrap iterations.

#### TABLE IV: Test-Set Performance on METABRIC (95% CI in Brackets)
| Model | AUROC [95% CI] | Brier Score [95% CI] | ECE [95% CI] | Calibration Slope [95% CI] | Calibration Intercept [95% CI] |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **NPI score (raw, uncalibrated)** | 0.720 [0.660, 0.778] | n/a | n/a | n/a | n/a |
| **NPI (recalibrated, fitted)** | 0.720 [0.660, 0.778] | 0.177 [0.158, 0.197] | 0.043 [0.028, 0.089] | 1.117 [0.785, 1.492] | 0.077 [−0.292, 0.458] |
| **Logistic regression (calibrated)**| **0.723 [0.662, 0.780]**| **0.173 [0.154, 0.194]**| **0.026 [0.025, 0.077]**| 1.143 [0.818, 1.586] | 0.125 [−0.268, 0.589] |
| **XGBoost (uncalibrated)** | 0.713 [0.655, 0.770] | 0.178 [0.158, 0.198] | 0.040 [0.027, 0.090] | 1.141 [0.802, 1.524] | 0.145 [−0.258, 0.587] |
| **XGBoost (calibrated)** | 0.714 [0.655, 0.770] | 0.179 [0.158, 0.200] | 0.063 [0.040, 0.113] | **0.967 [0.674, 1.301]** | **−0.033 [−0.409, 0.366]** |

### B. Hypotheses and Acceptance Criteria Evaluation
- **H1 (AUROC XGBoost $\ge$ Logistic): FAIL.** Calibrated XGBoost achieved AUROC 0.714 vs 0.723 for calibrated Logistic Regression (difference: $-0.0094$, 95% CI [$-0.0357, +0.0165$]). The linear model slightly outperformed the tree ensemble.
- **H2 (Calibrated XGBoost $\text{ECE} < 0.05$): FAIL.** Calibrated XGBoost had an ECE of 0.0629 (95% CI [0.040, 0.113]), exceeding the 0.05 threshold.
- **H3 (Calibration reduces XGBoost ECE): FAIL.** Uncalibrated XGBoost had an ECE of 0.0397, whereas Platt sigmoid scaling yielded an ECE of 0.0629. While Platt scaling improved the calibration slope from 1.141 toward ideal 0.967 and the intercept from 0.145 to $-0.033$, it increased bin-level error by over-shrinking intermediate probabilities.
- **A1 (Simultaneous NPI Comparison): PASS.** All four models and raw NPI were evaluated simultaneously on the identical 389 held-out test patients.
- **A2 (Property Tests R1–R4): PASS.** All 7 automated property and adversarial test suites passed without failure.
- **A3 (Latency p95 < 500 ms): PASS.** 95th-percentile response time was 16.50 ms under 1,000-request benchmark load.

### C. Software Verification (Table V)

#### TABLE V: Software Verification and Property-Based Results
| Check | Criterion | Result | Evidence / Details |
| :--- | :--- | :---: | :--- |
| **R1 Determinism** | Identical state hash across runs | **PASS** | 100/100 repeated rebuilds identical (`tests/test_properties.py`). |
| **R2 Order independence** | Identical state after permuting arrival order | **PASS** | 50/50 randomized arrival permutations produced identical state. |
| **R3 Idempotency** | Duplicate delivery rejected without mutation | **PASS** | `DuplicateEventError` raised on re-ingestion; state unaltered. |
| **R4 As-of consistency** | Later events do not alter earlier state | **PASS** | State at $\tau_c$ identical whether future events are present or absent. |
| **Adversarial late amendments** | Earlier clinical finding arrives after later event | **PASS** | Canonical fold correctly applies late-arriving resection pathology. |
| **Adversarial conflicts** | Identical timestamp contradictory labs | **PASS** | Deterministic event ID tie-breaker guarantees reproducible state. |
| **Re-execution audit** | Recomputed prediction matches within tolerance | **PASS** | Max diff LR: $0.00$ ($< 10^{-9}$), Max diff XGB: $0.00$ ($< 10^{-6}$). |
| **A3 Latency, p95** | Below 500 ms under stated load | **PASS** | $\text{p50}=12.24\text{ ms}$, $\text{p95}=16.50\text{ ms}$, $\text{p99}=19.39\text{ ms}$ (1,000 runs, x86-64). |

### D. Subgroup and Sensitivity Analysis
- **Subgroup Discrimination:** In ER-negative patients ($n=97$), discrimination was highest (XGBoost AUROC 0.771, Logistic 0.765, NPI 0.772). In ER-positive patients ($n=289$), discrimination was lower (XGBoost 0.665, Logistic 0.684, NPI 0.670). Patients over 65 ($n=155$) exhibited high discrimination across all models (NPI 0.824, Logistic 0.796, XGBoost 0.767).
- **IPCW Sensitivity Analysis:** Weighting test patients by the inverse probability of remaining uncensored at 60 months yielded a Brier score of 0.1787 for calibrated XGBoost (vs 0.1788 unweighted) and 0.1730 for calibrated Logistic Regression (vs 0.1735 unweighted). The difference ($< 0.0005$) confirms that censoring exclusion did not induce significant selection bias.

### E. External Validation Feasibility on TCGA-BRCA
External validation on TCGA-BRCA was evaluated and determined to be **infeasible**:
1. **Follow-up Truncation:** Median disease-free follow-up in TCGA-BRCA is only **25.0 months**. 677 of 941 patients (71.9%) with DFS data are censored prior to 60 months without recurrence. Only 74 recurrences and 190 recurrence-free patients reached 60 months.
2. **Feature Incompatibility:** TCGA clinical matrices record pathologic T stage (T1–T4) rather than continuous tumour diameter (mm), and histologic grade is absent for the vast majority of patients. Direct evaluation without non-standard imputation would introduce severe bias.

---

## VII. DISCUSSION AND LIMITATIONS

### A. Clinical Implications of the Empirical Finding
The empirical results reveal that neither calibrated logistic regression (AUROC 0.723) nor XGBoost (AUROC 0.714) provided a clinically meaningful improvement over the simple, uncalibrated NPI score (AUROC 0.720) on this standard clinical feature set. The Nottingham Prognostic Index, established over three decades ago by Galea et al. [14], captures the predominant prognostic variance contained in tumour size, nodal involvement, and grade. Adding age and receptor status via nonlinear gradient boosting offered no discrimination benefit. This negative finding is methodologically important: it demonstrates that algorithmic complexity cannot compensate for the absence of molecular or genomic markers.

### B. Traceability and Digital Twin Verification
The primary contribution of OncoTwin-BRCA lies in system architecture. By decoupling clinical effective time from system ingestion time and enforcing an immutable event log, the system guarantees verifiable provenance. Re-execution audits reproduced predictions bit-for-bit, while p95 response times remained below 20 ms.

### C. Limitations
1. **Retrospective Cohort:** METABRIC is retrospective, derived from multiple centers spanning 1977–2005 with variable historic systemic therapy protocols.
2. **Absence of Genomic Signatures:** Multi-gene signatures (such as Oncotype DX or MammaPrint) were not available for integration into the feature vector.
3. **Synthetic Event Replay:** Because METABRIC is structured as a cross-sectional table, event timestamps were assigned using clinical staging sequence offsets (biopsy $\to$ pathology $\to$ biomarkers $\to$ surveillance). Prospective clinical validation on true longitudinal EHR streams is required before clinical use.

---

## VIII. CONCLUSION
OncoTwin-BRCA demonstrates an event-sourced architecture for traceable breast-cancer recurrence risk prediction. The empirical evaluation on METABRIC highlights that complex tree-boosting models perform comparably to the established NPI on routine clinical variables, emphasizing the importance of calibration, auditability, and restrained claims in digital health engineering.

---

## REFERENCES
- [1] A. Asghar and C. Chung, "Application of digital twins for personalized oncology," *Nature Reviews Cancer*, vol. 25, no. 11, pp. 823–825, 2025.
- [2] C. Curtis, S. P. Shah, S.-F. Chin et al., "The genomic and transcriptomic architecture of 2,000 breast tumours reveals novel subgroups," *Nature*, vol. 486, pp. 346–352, 2012.
- [3] The Cancer Genome Atlas Network, "Comprehensive molecular portraits of human breast tumours," *Nature*, vol. 490, pp. 61–70, 2012.
- [4] National Academies of Sciences, Engineering, and Medicine, *Foundational Research Gaps and Future Directions for Digital Twins*. Washington, DC: National Academies Press, 2024.
- [5] E. Katsoulakis, Q. Wang, H. Wu et al., "Digital twins for health: A scoping review," *npj Digital Medicine*, vol. 7, p. 77, 2024.
- [6] K. P. Venkatesh, M. M. Raza, and J. C. Kvedar, "Health digital twins as tools for precision medicine: Considerations for computation, implementation, and regulation," *npj Digital Medicine*, vol. 5, p. 150, 2022.
- [7] R. Laubenbacher, B. Mehrad, I. Shmulevich, and N. Trayanova, "Digital twins in medicine," *Nature Computational Science*, vol. 4, pp. 184–191, 2024.
- [8] A. Niculescu-Mizil and R. Caruana, "Predicting good probabilities with supervised learning," in *Proc. 22nd Int. Conf. Machine Learning (ICML)*, 2005, pp. 625–632.
- [9] C. Guo, G. Pleiss, Y. Sun, and K. Q. Weinberger, "On calibration of modern neural networks," in *Proc. 34th Int. Conf. Machine Learning (ICML)*, vol. 70, 2017, pp. 1321–1330.
- [10] S. M. Lundberg and S.-I. Lee, "A unified approach to interpreting model predictions," in *Advances in Neural Information Processing Systems*, vol. 30, 2017, pp. 4765–4774.
- [11] C. Rudin, "Stop explaining black box machine learning models for high stakes decisions and use interpretable models instead," *Nature Machine Intelligence*, vol. 1, pp. 206–215, 2019.
- [12] D. Sculley, G. Holt, D. Golovin et al., "Hidden technical debt in machine learning systems," in *Advances in Neural Information Processing Systems*, vol. 28, 2015, pp. 2503–2511.
- [13] G. S. Collins, K. G. M. Moons, P. Dhiman et al., "TRIPOD+AI statement: Updated guidance for reporting clinical prediction models that use regression or machine learning methods," *BMJ*, vol. 385, e078378, 2024.
- [14] M. H. Galea, R. W. Blamey, C. E. Elston, and I. O. Ellis, "The Nottingham Prognostic Index in primary breast cancer," *Breast Cancer Research and Treatment*, vol. 22, no. 3, pp. 207–219, 1992.
- [15] M. Grieves and J. Vickers, "Digital twin: Mitigating unpredictable, undesirable emergent behavior in complex systems," in *Transdisciplinary Perspectives on Complex Systems*. Cham: Springer, 2017, pp. 85–113.
- [16] F. J. Candido dos Reis, G. C. Wishart, E. M. Dicks et al., "An updated PREDICT breast cancer prognostication and treatment benefit prediction model with independent validation," *Breast Cancer Research*, vol. 19, p. 58, 2017.
- [17] S. Paik, S. Shak, G. Tang et al., "A multigene assay to predict recurrence of tamoxifen-treated, node-negative breast cancer," *New England Journal of Medicine*, vol. 351, no. 27, pp. 2817–2826, 2004.
- [18] J. C. Platt, "Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods," in *Advances in Large Margin Classifiers*. Cambridge, MA: MIT Press, 1999, pp. 61–74.
- [19] G. W. Brier, "Verification of forecasts expressed in terms of probability," *Monthly Weather Review*, vol. 78, no. 1, pp. 1–3, 1950.
- [20] E. W. Steyerberg, *Clinical Prediction Models: A Practical Approach to Development, Validation, and Updating*, 2nd ed. Cham: Springer, 2019.
- [21] M. T. Ribeiro, S. Singh, and C. Guestrin, "'Why should I trust you?': Explaining the predictions of any classifier," in *Proc. 22nd ACM SIGKDD Int. Conf. Knowledge Discovery and Data Mining*, 2016, pp. 1135–1144.
- [22] Health Level Seven International, *HL7 FHIR Release 4 (v4.0.1): Observation and DiagnosticReport Resources*, 2019.
- [23] J. Walonoski, M. Kramer, J. Nichols et al., "Synthea: An approach, method, and software mechanism for generating synthetic patients and the synthetic electronic health record," *Journal of the American Medical Informatics Association*, vol. 25, no. 3, pp. 230–238, 2018.
- [24] M. Fowler, "Event sourcing," martinfowler.com, 2005.
- [25] L. Lamport, "Time, clocks, and the ordering of events in a distributed system," *Communications of the ACM*, vol. 21, no. 7, pp. 558–565, 1978.
- [26] M. Kleppmann, *Designing Data-Intensive Applications*. Sebastopol, CA: O'Reilly Media, 2017.
- [27] M. D. Wilkinson, M. Dumontier, I. J. Aalbersberg et al., "The FAIR Guiding Principles for scientific data management and stewardship," *Scientific Data*, vol. 3, p. 160018, 2016.
- [28] T. Chen and C. Guestrin, "XGBoost: A scalable tree boosting system," in *Proc. 22nd ACM SIGKDD Int. Conf. Knowledge Discovery and Data Mining (KDD)*, 2016, pp. 785–794.
- [29] National Cancer Institute, "The Cancer Genome Atlas Program and Genomic Data Commons: TCGA-BRCA," 2024.
- [30] K. Clark, B. Vendt, K. Smith et al., "The Cancer Imaging Archive (TCIA): Maintaining and operating a public information repository," *Journal of Digital Imaging*, vol. 26, pp. 1045–1057, 2013.
- [31] A. J. Vickers and E. B. Elkin, "Decision curve analysis: A novel method for evaluating prediction models," *Medical Decision Making*, vol. 26, no. 6, pp. 565–574, 2006.
- [32] S. M. Lundberg, G. Erion, H. Chen, A. DeGrave, J. M. Prutkin, B. Nair, R. Katz, M. Himer, N. Bansal, and S.-I. Lee, "From local explanations to global understanding with explainable AI for trees," *Nature Machine Intelligence*, vol. 2, no. 1, pp. 56–67, 2020.
