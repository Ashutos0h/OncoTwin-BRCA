# Ownership

| Lead | Owns | First handoff |
| --- | --- | --- |
| Frontend | frontend/ | Fixture dashboard → Backend API integration |
| Backend/Digital Twin | backend/ | Event acceptance/replay → snapshot and audit |
| AI/ML | ml/ | Validated snapshot → explicit mock prediction |
| Data/FHIR | data/ | Tested synthetic mapping → ClinicalEvent |

Backend owns application database migrations; Data reviews schema/provenance
requirements. contracts/, infra/, shared docs and root tooling need affected-lead
review. Each lead has a copyable task prompt in docs/leads/.
Use independent clones or worktrees; do not run four branch checkouts in one folder.
