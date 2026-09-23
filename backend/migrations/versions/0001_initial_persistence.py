"""Create persistent twin, event, snapshot, prediction, and audit tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial_persistence"
down_revision = None
branch_labels = None
depends_on = None

json_document = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "twins",
        sa.Column("twin_id", sa.String(length=255), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "clinical_events",
        sa.Column("event_id", sa.String(length=255), primary_key=True),
        sa.Column("twin_id", sa.String(length=255), sa.ForeignKey("twins.twin_id"), nullable=False),
        sa.Column("effective_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document", json_document, nullable=False),
    )
    op.create_index("ix_clinical_events_twin_id", "clinical_events", ["twin_id"])
    op.create_table(
        "feature_snapshots",
        sa.Column("snapshot_id", sa.String(length=255), primary_key=True),
        sa.Column("twin_id", sa.String(length=255), sa.ForeignKey("twins.twin_id"), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_ids", json_document, nullable=False),
        sa.Column("document", json_document, nullable=False),
    )
    op.create_index("ix_feature_snapshots_twin_id", "feature_snapshots", ["twin_id"])
    op.create_table(
        "predictions",
        sa.Column("prediction_id", sa.String(length=255), primary_key=True),
        sa.Column("twin_id", sa.String(length=255), sa.ForeignKey("twins.twin_id"), nullable=False),
        sa.Column(
            "snapshot_id",
            sa.String(length=255),
            sa.ForeignKey("feature_snapshots.snapshot_id"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document", json_document, nullable=False),
    )
    op.create_index("ix_predictions_twin_id", "predictions", ["twin_id"])
    op.create_table(
        "audit_records",
        sa.Column("audit_id", sa.String(length=255), primary_key=True),
        sa.Column("twin_id", sa.String(length=255), sa.ForeignKey("twins.twin_id"), nullable=False),
        sa.Column(
            "prediction_id",
            sa.String(length=255),
            sa.ForeignKey("predictions.prediction_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document", json_document, nullable=False),
    )
    op.create_index("ix_audit_records_twin_id", "audit_records", ["twin_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_records_twin_id", table_name="audit_records")
    op.drop_table("audit_records")
    op.drop_index("ix_predictions_twin_id", table_name="predictions")
    op.drop_table("predictions")
    op.drop_index("ix_feature_snapshots_twin_id", table_name="feature_snapshots")
    op.drop_table("feature_snapshots")
    op.drop_index("ix_clinical_events_twin_id", table_name="clinical_events")
    op.drop_table("clinical_events")
    op.drop_table("twins")
