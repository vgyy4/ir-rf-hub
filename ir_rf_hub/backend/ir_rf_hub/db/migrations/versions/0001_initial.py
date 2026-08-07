"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-04

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "esp_devices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer, nullable=False, server_default="6053"),
        sa.Column("encryption_key_enc", sa.LargeBinary, nullable=True),
        sa.Column("password_enc", sa.LargeBinary, nullable=True),
        sa.Column("mdns_name", sa.String(255), nullable=True),
        sa.Column("tx_settle_ms", sa.Integer, nullable=False, server_default="150"),
        sa.Column("rx_stop_settle_ms", sa.Integer, nullable=False, server_default="150"),
        sa.Column("connect_timeout_s", sa.Integer, nullable=False, server_default="10"),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "device_entities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "device_id",
            sa.String(36),
            sa.ForeignKey("esp_devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("esphome_key", sa.Integer, nullable=False),
        sa.Column("object_id", sa.String(255), nullable=False),
        sa.Column("domain", sa.Enum("infrared", "radio_frequency", name="signaldomain"), nullable=False),
        sa.Column("role", sa.Enum("tx", "rx", name="devicerole"), nullable=False),
        sa.Column("frequency_hz", sa.Integer, nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_device_entities_device_id", "device_entities", ["device_id"])

    op.create_table(
        "commands",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("type", sa.Enum("ir", "rf", name="signaltype"), nullable=False),
        sa.Column("raw_timings", sa.JSON, nullable=False),
        sa.Column("carrier_frequency_hz", sa.Integer, nullable=False, server_default="0"),
        sa.Column("modulation", sa.Enum("OOK", name="modulation"), nullable=False, server_default="OOK"),
        sa.Column("repeat_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "default_device_id",
            sa.String(36),
            sa.ForeignKey("esp_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "recorded_from_device_id",
            sa.String(36),
            sa.ForeignKey("esp_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_commands_name", "commands", ["name"])

    op.create_table(
        "settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("settings")
    op.drop_index("ix_commands_name", table_name="commands")
    op.drop_table("commands")
    op.drop_index("ix_device_entities_device_id", table_name="device_entities")
    op.drop_table("device_entities")
    op.drop_table("esp_devices")
