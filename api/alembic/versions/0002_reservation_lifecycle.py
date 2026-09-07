"""reservation lifecycle: cancelled_at / returned_at

Closing a reservation marks it instead of deleting the row, so the loan history
survives cancellations, returns and expiries.

Revision ID: 0002_reservation_lifecycle
Revises: 0001_initial
Create Date: 2026-09-07 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0002_reservation_lifecycle'
down_revision: Union[str, None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reservations", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "reservations", sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("reservations", "returned_at")
    op.drop_column("reservations", "cancelled_at")
