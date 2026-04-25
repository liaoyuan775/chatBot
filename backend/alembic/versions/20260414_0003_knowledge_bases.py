"""add knowledge bases and document binding

Revision ID: 20260414_0003
Revises: 20260414_0002
Create Date: 2026-04-14 18:10:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260414_0003"
down_revision: Union[str, None] = "20260414_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(length=80), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.add_column("knowledge_documents", sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_knowledge_documents_knowledge_base_id",
        "knowledge_documents",
        "knowledge_bases",
        ["knowledge_base_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_knowledge_documents_knowledge_base_id", "knowledge_documents", ["knowledge_base_id"])

    op.execute(
        """
        INSERT INTO knowledge_bases (name, description, is_default)
        SELECT '默认知识库', '系统默认知识库', true
        WHERE NOT EXISTS (SELECT 1 FROM knowledge_bases);
        """
    )
    op.execute(
        """
        UPDATE knowledge_documents
        SET knowledge_base_id = (
            SELECT id FROM knowledge_bases
            WHERE is_default = true
            ORDER BY created_at ASC
            LIMIT 1
        )
        WHERE knowledge_base_id IS NULL;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_documents_knowledge_base_id", table_name="knowledge_documents")
    op.drop_constraint("fk_knowledge_documents_knowledge_base_id", "knowledge_documents", type_="foreignkey")
    op.drop_column("knowledge_documents", "knowledge_base_id")
    op.drop_table("knowledge_bases")
