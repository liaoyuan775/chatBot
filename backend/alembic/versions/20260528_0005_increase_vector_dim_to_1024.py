"""increase embedding vector dimension from 8 to 1024 for BGE-M3 full output

Revision ID: 20260528_0005
Revises: 20260414_0004
Create Date: 2026-05-28 10:00:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260528_0005"
down_revision: Union[str, None] = "20260414_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # BGE-M3 outputs 1024-dimensional vectors; the old 8-dim truncation was lossy.
    # Existing vectors will be padded with zeros in the extra dimensions.
    # Re-embedding existing documents is recommended after this migration.
    op.execute("ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(1024) USING embedding::vector(1024)")
    op.execute("ALTER TABLE long_term_memories ALTER COLUMN embedding TYPE vector(1024) USING embedding::vector(1024)")


def downgrade() -> None:
    # Truncate back to 8 dimensions (lossy).
    op.execute("ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(8) USING embedding::vector(8)")
    op.execute("ALTER TABLE long_term_memories ALTER COLUMN embedding TYPE vector(8) USING embedding::vector(8)")
