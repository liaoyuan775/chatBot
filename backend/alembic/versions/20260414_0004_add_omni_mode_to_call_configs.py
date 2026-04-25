"""add omni_mode column to call_configs

Revision ID: 20260414_0004
Revises: 20260414_0003
Create Date: 2026-04-14 22:05:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260414_0004"
down_revision: Union[str, None] = "20260414_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {item["name"] for item in inspector.get_columns(table_name)}
    return column_name in columns


def upgrade() -> None:
    if not _has_column("call_configs", "omni_mode"):
        op.add_column(
            "call_configs",
            sa.Column("omni_mode", sa.String(length=32), nullable=False, server_default="auto"),
        )
    op.execute("UPDATE call_configs SET omni_mode = 'auto' WHERE omni_mode IS NULL OR omni_mode = ''")


def downgrade() -> None:
    if _has_column("call_configs", "omni_mode"):
        op.drop_column("call_configs", "omni_mode")

