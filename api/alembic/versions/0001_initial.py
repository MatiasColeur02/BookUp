"""initial schema: libraries, books, copies, reservations

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-04

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    copy_status = sa.Enum("available", "reserved", "loaned", name="copy_status")
    reservation_status = sa.Enum(
        "pending", "confirmed", "cancelled", "fulfilled", name="reservation_status"
    )

    op.create_table(
        "libraries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("city", sa.String(120), nullable=False),
        sa.Column("address", sa.String(300)),
    )

    op.create_table(
        "books",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("author", sa.String(200), nullable=False),
        sa.Column("isbn", sa.String(20), nullable=False, unique=True),
        sa.Column("synopsis", sa.Text),
    )
    op.create_index("ix_books_title", "books", ["title"])
    op.create_index("ix_books_author", "books", ["author"])
    op.create_index("ix_books_isbn", "books", ["isbn"])

    op.create_table(
        "copies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("book_id", sa.Integer, sa.ForeignKey("books.id"), nullable=False),
        sa.Column("library_id", sa.Integer, sa.ForeignKey("libraries.id"), nullable=False),
        sa.Column("status", copy_status, nullable=False, server_default="available"),
    )

    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("copy_id", sa.Integer, sa.ForeignKey("copies.id"), nullable=False),
        sa.Column("patron_name", sa.String(200), nullable=False),
        sa.Column("patron_email", sa.String(200), nullable=False),
        sa.Column("status", reservation_status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("confirmed_by", sa.String(200)),
    )


def downgrade() -> None:
    op.drop_table("reservations")
    op.drop_table("copies")
    op.drop_index("ix_books_isbn", table_name="books")
    op.drop_index("ix_books_author", table_name="books")
    op.drop_index("ix_books_title", table_name="books")
    op.drop_table("books")
    op.drop_table("libraries")
    sa.Enum(name="reservation_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="copy_status").drop(op.get_bind(), checkfirst=True)
