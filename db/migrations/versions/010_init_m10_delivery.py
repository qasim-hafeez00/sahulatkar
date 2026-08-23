"""Init M10 delivery

Revision ID: 010_init_m10_delivery
Revises: 009_init_m09_hitl
Create Date: 2026-04-12 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "010_init_m10_delivery"
down_revision: Union[str, None] = "009_init_m09_hitl"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "couriers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=20), nullable=False),
        sa.Column("tracking_url_template", sa.String(length=512), nullable=True),
        sa.Column("api_endpoint", sa.String(length=512), nullable=True),
        sa.Column("api_key_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("coverage_provinces", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_cod_available", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("avg_delivery_days", sa.SmallInteger(), server_default=sa.text("3"), nullable=False),
        sa.Column("aftership_slug", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.execute(
        """
        INSERT INTO couriers (name, code, aftership_slug, avg_delivery_days, is_active, is_cod_available)
        VALUES
          ('TCS', 'TCS', 'tcs-pak', 3, true, true),
          ('Leopards', 'LEO', 'leopards-courier', 3, true, true),
          ('M&P', 'MNP', 'm-and-p-pakistan', 4, true, true),
          ('PostEx', 'POSTEX', 'postex', 3, true, false),
          ('Swyft', 'SWYFT', 'swyft', 2, true, false)
        """
    )

    op.create_table(
        "shipments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("courier_id", sa.BigInteger(), nullable=True),
        sa.Column("courier_name", sa.String(length=100), nullable=True),
        sa.Column("tracking_number", sa.String(length=100), nullable=True),
        sa.Column("aftership_tracking_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), server_default=sa.text("'label_created'"), nullable=False),
        sa.Column("estimated_delivery", sa.Date(), nullable=True),
        sa.Column("actual_delivery", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('label_created','picked_up','in_transit','out_for_delivery','delivered','attempted','delivery_attempted','delivery_exception','returned','lost')",
            name="ck_shipments_status",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["courier_id"], ["couriers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
        sa.UniqueConstraint("order_id"),
        sa.UniqueConstraint("tracking_number"),
    )
    op.create_index("ix_shipments_order_id", "shipments", ["order_id"], unique=True)
    op.create_index("ix_shipments_status_created", "shipments", ["status", "created_at"], unique=False)

    op.create_table(
        "tracking_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shipment_id", sa.BigInteger(), nullable=False),
        sa.Column("event_code", sa.String(length=50), nullable=False),
        sa.Column("event_description", sa.Text(), nullable=True),
        sa.Column("location_city", sa.String(length=100), nullable=True),
        sa.Column("courier_raw_data", sa.JSON(), nullable=True),
        sa.Column("event_time", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        # TimescaleDB requires the partitioning column (event_time) to be part
        # of every unique/primary-key constraint before create_hypertable()
        # below will accept this table.
        sa.PrimaryKeyConstraint("id", "event_time"),
    )
    op.create_index("ix_tracking_events_shipment_id", "tracking_events", ["shipment_id"], unique=False)
    op.create_index("ix_tracking_events_event_time", "tracking_events", ["event_time"], unique=False)
    op.create_index("ix_tracking_events_shipment_time", "tracking_events", ["shipment_id", "event_time"], unique=False)

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                PERFORM create_hypertable('tracking_events', 'event_time', if_not_exists => TRUE);
                ALTER TABLE tracking_events SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = 'shipment_id',
                    timescaledb.compress_orderby = 'event_time'
                );
                PERFORM add_compression_policy('tracking_events', INTERVAL '7 days', if_not_exists => TRUE);
                PERFORM add_retention_policy('tracking_events', INTERVAL '2 years', if_not_exists => TRUE);
            END IF;
        EXCEPTION WHEN undefined_function THEN
            NULL;
        END;
        $$;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_tracking_events_shipment_time", table_name="tracking_events")
    op.drop_index("ix_tracking_events_event_time", table_name="tracking_events")
    op.drop_index("ix_tracking_events_shipment_id", table_name="tracking_events")
    op.drop_table("tracking_events")

    op.drop_index("ix_shipments_status_created", table_name="shipments")
    op.drop_index("ix_shipments_order_id", table_name="shipments")
    op.drop_table("shipments")

    op.drop_table("couriers")
