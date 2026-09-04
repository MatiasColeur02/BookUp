"""Populate the database with a small sample catalog for local development."""

from .persistence import models
from .persistence.database import Base, SessionLocal, engine


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(models.Library).count() > 0:
            print("Data already present, skipping seed.")
            return

        central = models.Library(name="Biblioteca Central", city="Buenos Aires", address="Av. Corrientes 1234")
        norte = models.Library(name="Biblioteca del Norte", city="Rosario", address="San Martín 500")
        db.add_all([central, norte])
        db.flush()

        books = [
            models.Book(
                title="Cien años de soledad",
                author="Gabriel García Márquez",
                isbn="9780307474728",
                synopsis="La saga de la familia Buendía en Macondo.",
            ),
            models.Book(
                title="Ficciones",
                author="Jorge Luis Borges",
                isbn="9788420633106",
                synopsis="Cuentos fantásticos y filosóficos.",
            ),
            models.Book(
                title="Rayuela",
                author="Julio Cortázar",
                isbn="9788437604572",
                synopsis="Novela experimental sobre Horacio Oliveira.",
            ),
        ]
        db.add_all(books)
        db.flush()

        db.add_all(
            [
                models.Copy(book_id=books[0].id, library_id=central.id),
                models.Copy(book_id=books[0].id, library_id=norte.id),
                models.Copy(book_id=books[1].id, library_id=central.id),
                models.Copy(book_id=books[2].id, library_id=norte.id),
            ]
        )
        db.commit()
        print("Sample data loaded.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
