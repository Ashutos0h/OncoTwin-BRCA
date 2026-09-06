# Shared contracts — provisional 0.1.0

These five schemas are the single interface source for this local scaffold.
The original ChatGPT conversation reported an attached contracts package, but its
schema contents were not retrievable. These are NEW reconstructed drafts, not a
verified copy of that package. No pre-existing local contracts were overwritten.
Before freezing the team baseline, compare the original package if recovered and
record a reviewed decision in docs/contract-decisions.md. Never silently replace it.

| Contract | Producer | Consumer |
| --- | --- | --- |
| ClinicalEvent | Data/FHIR | Backend |
| TwinState | Backend | Frontend |
| FeatureSnapshot | Backend | ML |
| Prediction | ML (backend supplies audit ID) | Backend, Frontend |
| AuditRecord | Backend | Frontend |

All examples describe the same synthetic twin and linked IDs. Times are RFC3339;
state versions are positive integers. Unknown values use null and missing_fields.
Payload/feature keys remain extensible; domain constraints and FHIR mappings still
need a reviewed feature dictionary. Schema validation is structural, not clinical.
An audit ID on an ML response reserves linkage; it does not prove persistence.
AuditRecord currently describes the prediction lifecycle; other actions may need
a reviewed conditional schema before implementation.

Run `python scripts/validate_contracts.py` from the root. Validation enables formats
and checks each schema itself. Tests also reject malformed payloads and broken demo
lineage. Breaking changes require producer/consumer review, versioning, fixture and
test updates, and a migration note. Module code must adapt to schemas, never edit
them merely to make a test pass.
