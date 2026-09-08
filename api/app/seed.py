"""Populate the database with a small sample catalog for local development."""

from .persistence import models
from .persistence.database import Base, SessionLocal, engine
from .services.auth_service import hash_password

# Development-only credentials: every seeded user shares this password.
SEED_PASSWORD = "bookup123"


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
        sur = models.Library(
            name="Biblioteca Sur",
            address="Av. Siempreviva 742",
            state="Buenos Aires",
            city="Quilmes",
            hours="L-V 9 a 18",
            phone="11-5555-0000",
            email="sur@bookup.example",
        )
        db.add_all([central, norte, sur])
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
                isbn="9788420633107",
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
                models.PhysicalBook(isbn=books[1].isbn, library_id=sur.id),
                models.PhysicalBook(isbn=books[2].isbn, library_id=sur.id),
            ]
        )
        # Without at least one sysadmin nobody can create libraries or staff
        # through the API, so the seed bootstraps one of each role.
        password_hash = hash_password(SEED_PASSWORD)
        db.add_all(
            [
                models.User(
                    email="admin@bookup.example",
                    password_hash=password_hash,
                    name="Sysadmin",
                    role=models.UserRole.sysadmin,
                ),
                models.User(
                    email="central@bookup.example",
                    password_hash=password_hash,
                    name="Bibliotecario Central",
                    role=models.UserRole.librarian,
                    library_id=central.id,
                ),
                models.User(
                    email="norte@bookup.example",
                    password_hash=password_hash,
                    name="Bibliotecario Norte",
                    role=models.UserRole.librarian,
                    library_id=norte.id,
                ),
                models.User(
                    email="sur@bookup.example",
                    password_hash=password_hash,
                    name="Bibliotecario Sur",
                    role=models.UserRole.librarian,
                    library_id=sur.id,
                ),
                models.User(
                    email="ana@bookup.example",
                    password_hash=password_hash,
                    name="Ana Lectora",
                    role=models.UserRole.customer,
                ),
            ]
        )
        db.commit()
        print(f"Sample data loaded. Seeded users share the password {SEED_PASSWORD!r}.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
