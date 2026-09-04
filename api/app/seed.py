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

        central = models.Library(
            name="Biblioteca Central",
            address="Av. Corrientes 1234",
            state="Buenos Aires",
            city="Buenos Aires",
        )
        norte = models.Library(
            name="Biblioteca del Norte",
            address="San Martín 500",
            state="Santa Fe",
            city="Rosario",
        )
        db.add_all([central, norte])
        db.flush()

        garcia_marquez = models.Author(name="Gabriel García Márquez")
        borges = models.Author(name="Jorge Luis Borges")
        cortazar = models.Author(name="Julio Cortázar")
        fiction = models.Genre(name="Ficción")
        db.add_all([garcia_marquez, borges, cortazar, fiction])
        db.flush()

        books = [
            models.Book(
                isbn="9780307474728",
                title="Cien años de soledad",
                language="es",
                synopsis="La saga de la familia Buendía en Macondo.",
                authors=[garcia_marquez],
                genres=[fiction],
            ),
            models.Book(
                isbn="9788420633106",
                title="Ficciones",
                language="es",
                synopsis="Cuentos fantásticos y filosóficos.",
                authors=[borges],
                genres=[fiction],
            ),
            models.Book(
                isbn="9788437604572",
                title="Rayuela",
                language="es",
                synopsis="Novela experimental sobre Horacio Oliveira.",
                authors=[cortazar],
                genres=[fiction],
            ),
        ]
        db.add_all(books)
        db.flush()

        db.add_all(
            [
                models.PhysicalBook(isbn=books[0].isbn, library_id=central.id),
                models.PhysicalBook(isbn=books[0].isbn, library_id=norte.id),
                models.PhysicalBook(isbn=books[1].isbn, library_id=central.id),
                models.PhysicalBook(isbn=books[2].isbn, library_id=norte.id),
            ]
        )
        db.commit()
        print("Sample data loaded.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
