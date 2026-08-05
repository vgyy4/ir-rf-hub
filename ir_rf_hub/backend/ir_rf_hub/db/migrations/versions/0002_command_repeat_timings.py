"""command repeat_timings + repeat_protocol

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-05

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("commands", sa.Column("repeat_timings", sa.JSON, nullable=True))
    op.add_column("commands", sa.Column("repeat_protocol", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("commands", "repeat_protocol")
    op.drop_column("commands", "repeat_timings")
