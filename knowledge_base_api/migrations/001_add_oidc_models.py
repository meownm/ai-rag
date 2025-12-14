"""Manual migration to add organizations and OIDC support columns."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
    )

    op.create_table(
        "user_organization_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
        sa.UniqueConstraint("user_id", "organization_id", name="uq_user_org"),
    )

    op.add_column("users", sa.Column("idp_subject", sa.String(), unique=True, nullable=True))
    op.alter_column("users", "hashed_password", existing_type=sa.String(), nullable=True)


def downgrade():
    op.drop_column("users", "idp_subject")
    op.drop_table("user_organization_roles")
    op.drop_table("organizations")
