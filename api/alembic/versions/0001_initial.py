"""initial schema: libraries, users, books, authors, genres, physical books, reservations

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
    user_role = sa.Enum("customer", "librarian", "sysadmin", name="user_role")
    physical_book_status = sa.Enum(
        "available", "reserved", "loaned", "lost", name="physical_book_status"
    )

    op.create_table(
        "libraries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("address", sa.String(255), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("hours", sa.String(255)),
        sa.Column("phone", sa.String(50)),
        sa.Column("email", sa.String(255)),
        sa.Column("website", sa.String(255)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("language", sa.String(10), nullable=False, server_default="es"),
        sa.Column("role", user_role, nullable=False),
        sa.Column("library_id", sa.Integer, sa.ForeignKey("libraries.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "books",
        sa.Column("isbn", sa.String(13), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("language", sa.String(50), nullable=False),
        sa.Column("pages", sa.Integer),
        sa.Column("synopsis", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_books_title", "books", ["title"])

    op.create_table(
        "authors",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
    )

    op.create_table(
        "genres",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
    )

    op.create_table(
        "book_authors",
        sa.Column("isbn", sa.String(13), sa.ForeignKey("books.isbn"), primary_key=True),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("authors.id"), primary_key=True),
    )

    op.create_table(
        "book_genres",
        sa.Column("isbn", sa.String(13), sa.ForeignKey("books.isbn"), primary_key=True),
        sa.Column("genre_id", sa.Integer, sa.ForeignKey("genres.id"), primary_key=True),
    )

    op.create_table(
        "physical_books",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("isbn", sa.String(13), sa.ForeignKey("books.isbn"), nullable=False),
        sa.Column("library_id", sa.Integer, sa.ForeignKey("libraries.id"), nullable=False),
        sa.Column(
            "status", physical_book_status, nullable=False, server_default="available"
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "physical_book_id", sa.Integer, sa.ForeignKey("physical_books.id"), nullable=False
        ),
        sa.Column(
            "reserved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("picked_up", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_table("reservations")
    op.drop_table("physical_books")
    op.drop_table("book_genres")
    op.drop_table("book_authors")
    op.drop_table("genres")
    op.drop_table("authors")
    op.drop_index("ix_books_title", table_name="books")
    op.drop_table("books")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_table("libraries")
    sa.Enum(name="physical_book_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="user_role").drop(op.get_bind(), checkfirst=True)
