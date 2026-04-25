"""add call config and chain audit tables

Revision ID: 20260414_0002
Revises: 20260414_0001
Create Date: 2026-04-14 12:20:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260414_0002"
down_revision: Union[str, None] = "20260414_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "call_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("main_provider", sa.String(length=64), nullable=False, server_default="dashscope"),
        sa.Column("main_model", sa.String(length=128), nullable=False, server_default="qwen3.5-omni-plus-realtime"),
        sa.Column("fallback_asr_provider", sa.String(length=64), nullable=False, server_default="siliconflow"),
        sa.Column("fallback_asr_model", sa.String(length=128), nullable=False, server_default="FunAudioLLM/SenseVoiceSmall"),
        sa.Column("fallback_llm_provider", sa.String(length=64), nullable=False, server_default="volcengine"),
        sa.Column("fallback_llm_model", sa.String(length=128), nullable=False, server_default="doubao-seed-1-6-251015"),
        sa.Column("fallback_tts_provider", sa.String(length=64), nullable=False, server_default="siliconflow"),
        sa.Column("fallback_tts_model", sa.String(length=128), nullable=False, server_default="FunAudioLLM/CosyVoice2-0.5B"),
        sa.Column("fallback_tts_voice", sa.String(length=128), nullable=False, server_default="FunAudioLLM/CosyVoice2-0.5B:alex"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "session_chain_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("chain_name", sa.String(length=64), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fail_reason", sa.Text(), nullable=True),
        sa.Column("trace_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("session_chain_audits")
    op.drop_table("call_configs")
