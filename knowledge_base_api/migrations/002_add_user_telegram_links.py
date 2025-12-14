"""Add user_telegram_links table"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    op.create_table(
        "user_telegram_links",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("state_token", sa.String(), nullable=False, unique=True),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("user_telegram_links")
