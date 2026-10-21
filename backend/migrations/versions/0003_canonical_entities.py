"""Create canonical entity tables for data foundation (PatientProfile, Observation, TumourProfile, ModelVersion, DataVersion)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_canonical_entities"
down_revision = "0002_twin_state_version"
branch_labels = None
depends_on = None

json_document = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    # 1. patient_profiles
    op.create_table(
        "patient_profiles",
        sa.Column("patient_id", sa.String(length=255), primary_key=True),
        sa.Column(
            "twin_id",
            sa.String(length=255),
            sa.ForeignKey("twins.twin_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("gender", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("birth_date", sa.String(length=32), nullable=True),
        sa.Column("mrn", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document", json_document, nullable=False),
    )
    op.create_index("ix_patient_profiles_twin_id", "patient_profiles", ["twin_id"])

    # 2. observations
    op.create_table(
        "observations",
        sa.Column("observation_id", sa.String(length=255), primary_key=True),
        sa.Column(
            "twin_id",
            sa.String(length=255),
            sa.ForeignKey("twins.twin_id"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False, server_default="pathology"),
        sa.Column("effective_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="final"),
        sa.Column("document", json_document, nullable=False),
    )
    op.create_index("ix_observations_twin_id", "observations", ["twin_id"])
    op.create_index("ix_observations_code", "observations", ["code"])
    op.create_index("ix_observations_effective_time", "observations", ["effective_time"])

    # 3. tumour_profiles
    op.create_table(
        "tumour_profiles",
        sa.Column("profile_id", sa.String(length=255), primary_key=True),
        sa.Column(
            "twin_id",
            sa.String(length=255),
            sa.ForeignKey("twins.twin_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("tumour_size_mm", sa.Float(), nullable=True),
        sa.Column("grade", sa.Integer(), nullable=True),
        sa.Column("positive_nodes", sa.Integer(), nullable=True),
        sa.Column("her2_status", sa.String(length=32), nullable=True),
        sa.Column("er_status", sa.String(length=32), nullable=True),
        sa.Column("pr_status", sa.String(length=32), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document", json_document, nullable=False),
    )
    op.create_index("ix_tumour_profiles_twin_id", "tumour_profiles", ["twin_id"])

    # 4. model_versions
    op.create_table(
        "model_versions",
        sa.Column("model_id", sa.String(length=255), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("algorithm", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("document", json_document, nullable=False),
    )
    op.create_index(
        "ix_model_versions_name_version", "model_versions", ["name", "version"]
    )

    # 5. data_versions
    op.create_table(
        "data_versions",
        sa.Column("data_version_id", sa.String(length=255), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("dataset_name", sa.String(length=128), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document", json_document, nullable=False),
    )
    op.create_index(
        "ix_data_versions_content_sha256", "data_versions", ["content_sha256"]
    )


def downgrade() -> None:
    op.drop_index("ix_data_versions_content_sha256", table_name="data_versions")
    op.drop_table("data_versions")
    op.drop_index("ix_model_versions_name_version", table_name="model_versions")
    op.drop_table("model_versions")
    op.drop_index("ix_tumour_profiles_twin_id", table_name="tumour_profiles")
    op.drop_table("tumour_profiles")
    op.drop_index("ix_observations_effective_time", table_name="observations")
    op.drop_index("ix_observations_code", table_name="observations")
    op.drop_index("ix_observations_twin_id", table_name="observations")
    op.drop_table("observations")
    op.drop_index("ix_patient_profiles_twin_id", table_name="patient_profiles")
    op.drop_table("patient_profiles")
