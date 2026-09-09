"""book cover: cover_key

Guarda la key del objeto en S3 (`covers/<isbn>/<uuid>.jpg`), no la URL: la URL pública
se arma al serializar, así mudar de bucket, de región o poner CloudFront adelante no
obliga a reescribir filas.

Revision ID: 0003_book_cover
Revises: 0002_reservation_lifecycle
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0003_book_cover'
down_revision: Union[str, None] = '0002_reservation_lifecycle'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("books", sa.Column("cover_key", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("books", "cover_key")
