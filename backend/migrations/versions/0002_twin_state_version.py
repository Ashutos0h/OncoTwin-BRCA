"""Add an atomically updated state version to twins."""

from alembic import op
import sqlalchemy as sa


revision = "0002_twin_state_version"
down_revision = "0001_initial_persistence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "twins",
        sa.Column("state_version", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute(
        "UPDATE twins SET state_version = "
        "(SELECT COUNT(*) FROM clinical_events WHERE clinical_events.twin_id = twins.twin_id)"
    )


def downgrade() -> None:
    op.drop_column("twins", "state_version")
