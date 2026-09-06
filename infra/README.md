# Optional local PostgreSQL

From repository root, copy `.env.example` to `.env` and choose a local password.
Run `docker compose --env-file .env -f infra/docker-compose.yml up -d`.
Check with `docker compose --env-file .env -f infra/docker-compose.yml ps`.
Stop with `docker compose --env-file .env -f infra/docker-compose.yml down`.
The named volume retains data. Do not remove it unless intentional.
The starter API does not use this database yet. Backend owns application migrations;
Data/FHIR reviews source/provenance and data storage requirements with Backend.
