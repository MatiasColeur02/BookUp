"""Populate the database with a rich sample dataset for local development.

El dataset es **determinista**: la distribución de ejemplares y reservas sale de un
`random.Random(RANDOM_SEED)`, así que dos corridas sobre bases limpias dan exactamente
lo mismo y un bug reproduce igual en cualquier máquina.

Los datos de catálogo (sedes, autores, géneros, libros) son fijos y están declarados
como tablas al principio del módulo; lo aleatorio es sólo el "ruido" operativo: qué
sede tiene qué ejemplar y qué reservas circularon por él.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from .persistence import models
from .persistence.database import Base, SessionLocal, engine
from .services.auth_service import hash_password

# Development-only credentials: every seeded user shares this password.
SEED_PASSWORD = "bookup123"

# Semilla del RNG: cambiarla regenera otro dataset igual de válido.
RANDOM_SEED = 20240501


def _isbn13(prefix: str) -> str:
    """Completa un ISBN-13 con su dígito verificador.

    Las tablas de abajo guardan los 12 primeros dígitos y el check digit se calcula acá,
    así que ningún libro del seed puede quedar con un ISBN que `POST /books` rechazaría.
    """
    if len(prefix) != 12 or not prefix.isdigit():
        raise ValueError(f"ISBN prefix must be 12 digits, got {prefix!r}")
    total = sum(int(digit) * (1 if index % 2 == 0 else 3) for index, digit in enumerate(prefix))
    return prefix + str((10 - total % 10) % 10)


# --------------------------------------------------------------------------- sedes
# (key, nombre, dirección, provincia, ciudad, horario, teléfono, sitio)
LIBRARIES: list[tuple[str, str, str, str, str, str, str, str]] = [
    (
        "central", "Biblioteca Central", "Av. Corrientes 1234", "Buenos Aires",
        "Buenos Aires", "L-V 8 a 20, S 9 a 14", "011-4555-1000", "https://central.bookup.example",
    ),
    (
        "norte", "Biblioteca del Norte", "San Martín 500", "Santa Fe",
        "Rosario", "L-V 9 a 19", "0341-455-2000", "https://norte.bookup.example",
    ),
    (
        "sur", "Biblioteca Sur", "Av. Siempreviva 742", "Buenos Aires",
        "Quilmes", "L-V 9 a 18", "011-5555-0000", "https://sur.bookup.example",
    ),
    (
        "cordoba", "Biblioteca Córdoba Capital", "Av. Colón 850", "Córdoba",
        "Córdoba", "L-V 8 a 21, S 10 a 16", "0351-422-3000", "https://cordoba.bookup.example",
    ),
    (
        "mendoza", "Biblioteca San Martín", "Av. San Martín 1450", "Mendoza",
        "Mendoza", "L-V 9 a 19", "0261-429-4000", "https://mendoza.bookup.example",
    ),
    (
        "plata", "Biblioteca de La Plata", "Calle 7 nro. 480", "Buenos Aires",
        "La Plata", "L-V 8 a 20", "0221-483-5000", "https://laplata.bookup.example",
    ),
    (
        "mardel", "Biblioteca del Mar", "Bv. Marítimo 2200", "Buenos Aires",
        "Mar del Plata", "L-D 10 a 20", "0223-495-6000", "https://mardel.bookup.example",
    ),
    (
        "salta", "Biblioteca del Norte Andino", "Caseros 620", "Salta",
        "Salta", "L-V 8 a 18", "0387-431-7000", "https://salta.bookup.example",
    ),
    (
        "neuquen", "Biblioteca Patagonia", "Av. Argentina 340", "Neuquén",
        "Neuquén", "L-V 9 a 18", "0299-442-8000", "https://patagonia.bookup.example",
    ),
    (
        "tucuman", "Biblioteca Bicentenario", "25 de Mayo 210", "Tucumán",
        "San Miguel de Tucumán", "L-V 8 a 19, S 9 a 13", "0381-430-9000",
        "https://tucuman.bookup.example",
    ),
]

# -------------------------------------------------------------------------- géneros
GENRES: list[str] = [
    "Ficción",
    "Novela",
    "Cuento",
    "Poesía",
    "Ensayo",
    "Ciencia ficción",
    "Fantasía",
    "Policial",
    "Terror",
    "Historia",
    "Ciencia",
    "Filosofía",
    "Biografía",
    "Infantil",
    "Divulgación",
    "Clásicos",
]

# --------------------------------------------------------------------------- autores
# (key, nombre)
AUTHORS: list[tuple[str, str]] = [
    ("garcia_marquez", "Gabriel García Márquez"),
    ("borges", "Jorge Luis Borges"),
    ("cortazar", "Julio Cortázar"),
    ("sabato", "Ernesto Sabato"),
    ("allende", "Isabel Allende"),
    ("vargas_llosa", "Mario Vargas Llosa"),
    ("bolano", "Roberto Bolaño"),
    ("rulfo", "Juan Rulfo"),
    ("paz", "Octavio Paz"),
    ("neruda", "Pablo Neruda"),
    ("benedetti", "Mario Benedetti"),
    ("galeano", "Eduardo Galeano"),
    ("lorca", "Federico García Lorca"),
    ("cervantes", "Miguel de Cervantes"),
    ("orwell", "George Orwell"),
    ("huxley", "Aldous Huxley"),
    ("austen", "Jane Austen"),
    ("bronte", "Emily Brontë"),
    ("dostoievski", "Fiódor Dostoievski"),
    ("tolstoi", "León Tolstói"),
    ("kafka", "Franz Kafka"),
    ("camus", "Albert Camus"),
    ("hesse", "Hermann Hesse"),
    ("tolkien", "J. R. R. Tolkien"),
    ("rowling", "J. K. Rowling"),
    ("martin", "George R. R. Martin"),
    ("herbert", "Frank Herbert"),
    ("asimov", "Isaac Asimov"),
    ("bradbury", "Ray Bradbury"),
    ("gibson", "William Gibson"),
    ("le_guin", "Ursula K. Le Guin"),
    ("christie", "Agatha Christie"),
    ("doyle", "Arthur Conan Doyle"),
    ("king", "Stephen King"),
    ("eco", "Umberto Eco"),
    ("saramago", "José Saramago"),
    ("murakami", "Haruki Murakami"),
    ("hemingway", "Ernest Hemingway"),
    ("fitzgerald", "F. Scott Fitzgerald"),
    ("salinger", "J. D. Salinger"),
    ("wilde", "Oscar Wilde"),
    ("verne", "Julio Verne"),
    ("shakespeare", "William Shakespeare"),
    ("homero", "Homero"),
    ("harari", "Yuval Noah Harari"),
    ("kahneman", "Daniel Kahneman"),
    ("sagan", "Carl Sagan"),
    ("hawking", "Stephen Hawking"),
    ("dawkins", "Richard Dawkins"),
    ("gladwell", "Malcolm Gladwell"),
    ("saint_exupery", "Antoine de Saint-Exupéry"),
    ("lindgren", "Astrid Lindgren"),
    ("frank", "Ana Frank"),
]

# ---------------------------------------------------------------------------- libros
# (isbn12, título, [autores], [géneros], páginas, idioma, sinopsis)
BOOKS: list[tuple[str, str, list[str], list[str], int, str, str]] = [
    (
        "978030747472", "Cien años de soledad", ["garcia_marquez"], ["Ficción", "Novela"],
        417, "es", "La saga de la familia Buendía a lo largo de siete generaciones en Macondo.",
    ),
    (
        "978030738973", "El amor en los tiempos del cólera", ["garcia_marquez"], ["Novela"],
        368, "es", "Florentino Ariza espera cincuenta años para volver a declararse a Fermina Daza.",
    ),
    (
        "978140003471", "Crónica de una muerte anunciada", ["garcia_marquez"],
        ["Novela", "Policial"], 120, "es",
        "Un pueblo entero sabe que van a matar a Santiago Nasar y nadie lo evita.",
    ),
    (
        "978842063310", "Ficciones", ["borges"], ["Cuento", "Ficción"], 174, "es",
        "Laberintos, bibliotecas infinitas y libros imposibles en los cuentos de Borges.",
    ),
    (
        "978843970101", "El Aleph", ["borges"], ["Cuento", "Ficción"], 146, "es",
        "El punto del espacio que contiene todos los puntos, y otros diecisiete relatos.",
    ),
    (
        "978843760457", "Rayuela", ["cortazar"], ["Novela", "Ficción"], 736, "es",
        "La novela que se puede leer en dos órdenes: Horacio Oliveira entre París y Buenos Aires.",
    ),
    (
        "978843760460", "Bestiario", ["cortazar"], ["Cuento"], 168, "es",
        "Ocho relatos donde lo fantástico se filtra en la vida cotidiana.",
    ),
    (
        "978843760224", "El túnel", ["sabato"], ["Novela", "Policial"], 158, "es",
        "El pintor Juan Pablo Castel narra desde la cárcel por qué mató a María Iribarne.",
    ),
    (
        "978843760320", "Sobre héroes y tumbas", ["sabato"], ["Novela"], 496, "es",
        "Buenos Aires, la familia Olmos y el célebre «Informe sobre ciegos».",
    ),
    (
        "978842332356", "La casa de los espíritus", ["allende"], ["Novela", "Ficción"],
        448, "es", "Cuatro generaciones de la familia Trueba entre lo íntimo y lo político.",
    ),
    (
        "978843392112", "La ciudad y los perros", ["vargas_llosa"], ["Novela"], 408, "es",
        "La violencia y los códigos internos del colegio militar Leoncio Prado.",
    ),
    (
        "978843392200", "La fiesta del Chivo", ["vargas_llosa"], ["Novela", "Historia"],
        520, "es", "Los últimos días de la dictadura de Trujillo en República Dominicana.",
    ),
    (
        "978843392500", "Los detectives salvajes", ["bolano"], ["Novela"], 609, "es",
        "Dos poetas real visceralistas buscan a Cesárea Tinajero por medio mundo.",
    ),
    (
        "978843392600", "2666", ["bolano"], ["Novela"], 1125, "es",
        "Cinco novelas entrelazadas alrededor de los crímenes de Santa Teresa.",
    ),
    (
        "978843761111", "Pedro Páramo", ["rulfo"], ["Novela", "Ficción"], 128, "es",
        "Juan Preciado llega a Comala a buscar a su padre y encuentra un pueblo de muertos.",
    ),
    (
        "978968160121", "El laberinto de la soledad", ["paz"], ["Ensayo", "Filosofía"],
        351, "es", "Ensayo fundacional sobre la identidad y la máscara del mexicano.",
    ),
    (
        "978843761222", "Veinte poemas de amor y una canción desesperada", ["neruda"],
        ["Poesía"], 96, "es", "El poemario más leído de Neruda, escrito a los veinte años.",
    ),
    (
        "978843761333", "La tregua", ["benedetti"], ["Novela"], 192, "es",
        "El diario de Martín Santomé, un oficinista a un año de jubilarse.",
    ),
    (
        "978968232361", "Las venas abiertas de América Latina", ["galeano"],
        ["Ensayo", "Historia"], 380, "es",
        "Cinco siglos de saqueo del continente contados como una sola historia.",
    ),
    (
        "978843760900", "Romancero gitano", ["lorca"], ["Poesía"], 128, "es",
        "Dieciocho romances donde Andalucía, la luna y la muerte son personajes.",
    ),
    (
        "978842043316", "Don Quijote de la Mancha", ["cervantes"], ["Novela", "Clásicos"],
        1250, "es", "Un hidalgo enloquecido por los libros de caballerías sale a desfacer entuertos.",
    ),
    (
        "978045152493", "1984", ["orwell"], ["Ciencia ficción", "Ficción"], 328, "es",
        "Winston Smith reescribe el pasado para un Partido que todo lo vigila.",
    ),
    (
        "978045216624", "Rebelión en la granja", ["orwell"], ["Ficción", "Clásicos"],
        112, "es", "Los animales toman la granja y descubren que algunos son más iguales que otros.",
    ),
    (
        "978006085052", "Un mundo feliz", ["huxley"], ["Ciencia ficción"], 288, "es",
        "Una sociedad diseñada para la felicidad obligatoria, sin dolor y sin arte.",
    ),
    (
        "978014143951", "Orgullo y prejuicio", ["austen"], ["Novela", "Clásicos"], 435, "es",
        "Elizabeth Bennet y el señor Darcy, entre malentendidos y buenos modales.",
    ),
    (
        "978014143955", "Cumbres borrascosas", ["bronte"], ["Novela", "Clásicos"], 416, "es",
        "El amor destructivo de Heathcliff y Catherine en los páramos de Yorkshire.",
    ),
    (
        "978014044913", "Crimen y castigo", ["dostoievski"], ["Novela", "Clásicos"],
        671, "es", "Raskólnikov mata a una usurera para probar una teoría y no soporta la culpa.",
    ),
    (
        "978014044927", "Los hermanos Karamázov", ["dostoievski"], ["Novela", "Filosofía"],
        796, "es", "Un parricidio y cuatro hermanos discutiendo a Dios, la culpa y la libertad.",
    ),
    (
        "978014044917", "Anna Karenina", ["tolstoi"], ["Novela", "Clásicos"], 864, "es",
        "El adulterio de Anna y la búsqueda de sentido de Levin en la Rusia zarista.",
    ),
    (
        "978014044941", "Guerra y paz", ["tolstoi"], ["Novela", "Historia"], 1225, "es",
        "Cinco familias rusas atravesadas por la invasión napoleónica.",
    ),
    (
        "978055321369", "La metamorfosis", ["kafka"], ["Cuento", "Ficción"], 96, "es",
        "Gregor Samsa amanece convertido en un insecto monstruoso.",
    ),
    (
        "978080520514", "El proceso", ["kafka"], ["Novela"], 255, "es",
        "Josef K. es procesado por un delito que nadie le explica.",
    ),
    (
        "978067972020", "El extranjero", ["camus"], ["Novela", "Filosofía"], 159, "es",
        "Meursault mata a un hombre bajo el sol de Argel y se niega a fingir dolor.",
    ),
    (
        "978067972021", "La peste", ["camus"], ["Novela", "Filosofía"], 308, "es",
        "Orán queda en cuarentena y cada quien decide qué hacer con la solidaridad.",
    ),
    (
        "978055320884", "Siddhartha", ["hesse"], ["Novela", "Filosofía"], 152, "es",
        "El viaje de un joven brahmán en busca de la iluminación por su cuenta.",
    ),
    (
        "978061826027", "El hobbit", ["tolkien"], ["Fantasía", "Infantil"], 310, "es",
        "Bilbo Bolsón sale de la Comarca con trece enanos a recuperar un tesoro.",
    ),
    (
        "978061826028", "El señor de los anillos", ["tolkien"], ["Fantasía"], 1216, "es",
        "La Comunidad del Anillo cruza la Tierra Media para destruir el Anillo Único.",
    ),
    (
        "978843841001", "Harry Potter y la piedra filosofal", ["rowling"],
        ["Fantasía", "Infantil"], 264, "es",
        "Un chico descubre a los once años que es mago y que lo esperan en Hogwarts.",
    ),
    (
        "978849793003", "Juego de tronos", ["martin"], ["Fantasía"], 800, "es",
        "Siete reinos, varias casas nobles y un invierno que se viene.",
    ),
    (
        "978044117271", "Dune", ["herbert"], ["Ciencia ficción"], 688, "es",
        "Paul Atreides y la lucha por Arrakis, el único planeta que produce la especia.",
    ),
    (
        "978055329335", "Fundación", ["asimov"], ["Ciencia ficción"], 244, "es",
        "La psicohistoria de Hari Seldon intenta acortar treinta mil años de barbarie.",
    ),
    (
        "978055338256", "Yo, robot", ["asimov"], ["Ciencia ficción", "Cuento"], 253, "es",
        "Nueve relatos que ponen a prueba las tres leyes de la robótica.",
    ),
    (
        "978145167331", "Fahrenheit 451", ["bradbury"], ["Ciencia ficción"], 194, "es",
        "Montag es bombero: su trabajo es quemar libros, hasta que abre uno.",
    ),
    (
        "978044156956", "Neuromante", ["gibson"], ["Ciencia ficción"], 271, "es",
        "La novela que fundó el cyberpunk: Case vuelve a conectarse a la matriz.",
    ),
    (
        "978006125425", "La mano izquierda de la oscuridad", ["le_guin"],
        ["Ciencia ficción"], 304, "es",
        "Un enviado terrestre en un planeta donde el género no es fijo.",
    ),
    (
        "978006207348", "Diez negritos", ["christie"], ["Policial"], 272, "es",
        "Diez desconocidos en una isla y una acusación que los va matando de a uno.",
    ),
    (
        "978006207350", "Asesinato en el Orient Express", ["christie"], ["Policial"],
        256, "es", "Poirot resuelve un crimen en un tren detenido por la nieve.",
    ),
    (
        "978014043908", "Estudio en escarlata", ["doyle"], ["Policial", "Clásicos"],
        176, "es", "El caso en el que Watson conoce a Sherlock Holmes.",
    ),
    (
        "978030774365", "El resplandor", ["king"], ["Terror"], 447, "es",
        "El hotel Overlook pasa el invierno vacío, con la familia Torrance adentro.",
    ),
    (
        "978145016962", "It", ["king"], ["Terror"], 1138, "es",
        "Siete chicos de Derry enfrentan algo que vuelve cada veintisiete años.",
    ),
    (
        "978015603863", "El nombre de la rosa", ["eco"], ["Novela", "Policial"], 536, "es",
        "Una abadía medieval, una biblioteca laberíntica y una serie de muertes.",
    ),
    (
        "978015600775", "Ensayo sobre la ceguera", ["saramago"], ["Novela", "Ficción"],
        352, "es", "Una epidemia de ceguera blanca desarma una ciudad entera.",
    ),
    (
        "978030727474", "Tokio blues", ["murakami"], ["Novela"], 296, "es",
        "Toru Watanabe recuerda su juventud en el Tokio de los sesenta.",
    ),
    (
        "978140077927", "Kafka en la orilla", ["murakami"], ["Novela", "Ficción"],
        480, "es", "Un chico que se escapa de casa y un viejo que habla con los gatos.",
    ),
    (
        "978068480122", "El viejo y el mar", ["hemingway"], ["Novela", "Clásicos"],
        127, "es", "Santiago pelea tres días con el pez más grande que vio en su vida.",
    ),
    (
        "978074327356", "El gran Gatsby", ["fitzgerald"], ["Novela", "Clásicos"], 180, "es",
        "Las fiestas de Gatsby, la luz verde del muelle y una época que se termina.",
    ),
    (
        "978031676948", "El guardián entre el centeno", ["salinger"], ["Novela"], 277, "es",
        "Tres días de Holden Caulfield sueltos por Nueva York.",
    ),
    (
        "978014143957", "El retrato de Dorian Gray", ["wilde"], ["Novela", "Clásicos"],
        272, "es", "El cuadro envejece y peca por él.",
    ),
    (
        "978014036721", "Veinte mil leguas de viaje submarino", ["verne"],
        ["Ficción", "Infantil"], 384, "es",
        "El capitán Nemo y el Nautilus recorren los océanos del mundo.",
    ),
    (
        "978074347712", "Hamlet", ["shakespeare"], ["Clásicos"], 342, "es",
        "El príncipe de Dinamarca duda entre vengar a su padre y no hacer nada.",
    ),
    (
        "978014026886", "La Odisea", ["homero"], ["Poesía", "Clásicos"], 541, "es",
        "Diez años le lleva a Ulises volver a Ítaca.",
    ),
    (
        "978015601219", "El principito", ["saint_exupery"], ["Infantil", "Ficción"],
        96, "es", "Un aviador varado en el desierto conoce a un chico que viene de un asteroide.",
    ),
    (
        "978014030957", "Pippi Calzaslargas", ["lindgren"], ["Infantil"], 160, "es",
        "La chica más fuerte del mundo vive sola con un mono y un caballo.",
    ),
    (
        "978006231609", "Sapiens: de animales a dioses", ["harari"],
        ["Ensayo", "Historia", "Divulgación"], 496, "es",
        "Cómo una especie más de primates terminó dominando el planeta.",
    ),
    (
        "978006246431", "Homo Deus", ["harari"], ["Ensayo", "Divulgación"], 464, "es",
        "Qué se propone la humanidad ahora que resolvió el hambre y la peste.",
    ),
    (
        "978037453355", "Pensar rápido, pensar despacio", ["kahneman"],
        ["Ensayo", "Ciencia", "Divulgación"], 499, "es",
        "Los dos sistemas con los que decidimos, y por qué uno nos engaña.",
    ),
    (
        "978034553943", "Cosmos", ["sagan"], ["Ciencia", "Divulgación"], 396, "es",
        "El universo contado desde el Big Bang hasta la vida en la Tierra.",
    ),
    (
        "978055338016", "Breve historia del tiempo", ["hawking"], ["Ciencia", "Divulgación"],
        212, "es", "Agujeros negros, relatividad y el origen del universo sin una sola ecuación.",
    ),
    (
        "978019929114", "El gen egoísta", ["dawkins"], ["Ciencia", "Divulgación"], 360, "es",
        "La evolución vista desde el punto de vista del gen, no del individuo.",
    ),
    (
        "978031601792", "Fueras de serie", ["gladwell"], ["Ensayo", "Divulgación"],
        320, "es", "Por qué el talento solo no alcanza para explicar el éxito.",
    ),
    (
        "978014118776", "El diario de Ana Frank", ["frank"], ["Biografía", "Historia"],
        283, "es", "Dos años de encierro en Ámsterdam contados por una adolescente.",
    ),
]

# ------------------------------------------------------------------------- usuarios
# (email local-part, nombre) — el rol customer es el del auto-registro.
CUSTOMERS: list[tuple[str, str]] = [
    ("ana", "Ana Lectora"),
    ("bruno", "Bruno Pereyra"),
    ("carla", "Carla Giménez"),
    ("diego", "Diego Fernández"),
    ("elena", "Elena Ruiz"),
    ("facundo", "Facundo Molina"),
    ("gabriela", "Gabriela Sosa"),
    ("hernan", "Hernán Quiroga"),
    ("irene", "Irene Bustos"),
    ("joaquin", "Joaquín Vega"),
    ("karina", "Karina Ledesma"),
    ("lucas", "Lucas Ibarra"),
    ("martina", "Martina Correa"),
    ("nicolas", "Nicolás Ayala"),
    ("olivia", "Olivia Ferrer"),
    ("pablo", "Pablo Ledesma"),
    ("rocio", "Rocío Maidana"),
    ("santiago", "Santiago Duarte"),
    ("tamara", "Tamara Ojeda"),
    ("valentin", "Valentín Ríos"),
]

# Nombre del bibliotecario a cargo de cada sede, por key de LIBRARIES.
LIBRARIANS: dict[str, str] = {
    "central": "Bibliotecario Central",
    "norte": "Bibliotecario Norte",
    "sur": "Bibliotecario Sur",
    "cordoba": "Mariana Robledo",
    "mendoza": "Esteban Aguirre",
    "plata": "Sofía Peralta",
    "mardel": "Damián Correa",
    "salta": "Lorena Chávez",
    "neuquen": "Matías Painé",
    "tucuman": "Verónica Juárez",
}

# Cuántas reservas generar de cada tipo. Cubre el ciclo de vida completo para que el
# panel del bibliotecario y «Mis reservas» tengan algo que mostrar en todos los estados.
RESERVATION_PLAN: dict[str, int] = {
    "returned": 90,   # cerradas por devolución (el ejemplar volvió a `available`)
    "cancelled": 25,  # canceladas antes del retiro
    "expired": 18,    # vencidas sin retirar: `cancelled_at` en el vencimiento
    "loaned": 30,     # abiertas y retiradas (ejemplar `loaned`), algunas en mora
    "reserved": 26,   # abiertas sin retirar (ejemplar `reserved`)
}


def _build_catalog(db) -> tuple[dict, dict, list]:
    libraries = {}
    for key, name, address, state, city, hours, phone, website in LIBRARIES:
        libraries[key] = models.Library(
            name=name,
            address=address,
            state=state,
            city=city,
            hours=hours,
            phone=phone,
            email=f"{key}@bookup.example",
            website=website,
        )
    db.add_all(libraries.values())

    genres = {name: models.Genre(name=name) for name in GENRES}
    authors = {key: models.Author(name=name) for key, name in AUTHORS}
    db.add_all(genres.values())
    db.add_all(authors.values())

    books = []
    for isbn12, title, author_keys, genre_names, pages, language, synopsis in BOOKS:
        books.append(
            models.Book(
                isbn=_isbn13(isbn12),
                title=title,
                language=language,
                pages=pages,
                synopsis=synopsis,
                authors=[authors[key] for key in author_keys],
                genres=[genres[name] for name in genre_names],
            )
        )
    db.add_all(books)
    db.flush()
    return libraries, genres, books


def _build_copies(db, rng: random.Random, libraries: dict, books: list) -> list:
    """Reparte ejemplares: cada libro está en varias sedes, con más de una copia a veces.

    Los títulos más pedidos (los primeros de la lista) se distribuyen a más sedes, así
    la pantalla de disponibilidad muestra stock cruzado de verdad.
    """
    branches = list(libraries.values())
    copies = []
    for index, book in enumerate(books):
        popular = index < 15
        branch_count = rng.randint(4, 7) if popular else rng.randint(1, 4)
        for branch in rng.sample(branches, branch_count):
            for _ in range(rng.randint(1, 3) if popular else rng.randint(1, 2)):
                copies.append(models.PhysicalBook(isbn=book.isbn, library_id=branch.id))
    db.add_all(copies)
    db.flush()
    return copies


def _build_users(db, libraries: dict) -> list:
    """Bootstrapea el staff y los lectores.

    Sin al menos un `sysadmin` nadie puede crear sedes ni personal por la API, así que
    el seed lo crea a mano: es el único punto donde se saltea esa regla.
    """
    password_hash = hash_password(SEED_PASSWORD)
    staff = [
        models.User(
            email="admin@bookup.example",
            password_hash=password_hash,
            name="Sysadmin",
            role=models.UserRole.sysadmin,
        ),
        models.User(
            email="soporte@bookup.example",
            password_hash=password_hash,
            name="Soporte BookUp",
            role=models.UserRole.sysadmin,
        ),
    ]
    for key, name in LIBRARIANS.items():
        staff.append(
            models.User(
                email=f"{key}@bookup.example",
                password_hash=password_hash,
                name=name,
                role=models.UserRole.librarian,
                library_id=libraries[key].id,
            )
        )

    customers = [
        models.User(
            email=f"{local_part}@bookup.example",
            password_hash=password_hash,
            name=name,
            role=models.UserRole.customer,
        )
        for local_part, name in CUSTOMERS
    ]

    db.add_all(staff)
    db.add_all(customers)
    db.flush()
    return customers


def _build_reservations(
    db, rng: random.Random, customers: list, copies: list, demo_library_ids: set[int]
) -> list:
    """Genera historial y reservas vivas, dejando el `status` del ejemplar consistente.

    Un ejemplar puede tener muchas reservas cerradas (ya circuló) pero como máximo una
    abierta: esa es la que fija su estado en `reserved` o `loaned`.
    """
    now = datetime.now(timezone.utc)
    reservations: list[models.Reservation] = []
    rng.shuffle(copies)

    # Las reservas abiertas se cargan hacia las tres sedes del README: son las que se
    # usan para probar el panel del bibliotecario, y repartidas parejo entre diez sedes
    # quedaban dos o tres por sede.
    demo_free = [copy for copy in copies if copy.library_id in demo_library_ids]
    other_free = [copy for copy in copies if copy.library_id not in demo_library_ids]

    def take_free() -> models.PhysicalBook | None:
        pool = demo_free if demo_free and rng.random() < 0.6 else other_free
        if not pool:
            pool = demo_free or other_free
        return pool.pop() if pool else None

    # Primero las cerradas: pueden caer sobre cualquier ejemplar, incluso uno que después
    # quede reservado de nuevo — es exactamente el caso "este libro ya circuló".
    for kind, amount in (
        ("returned", RESERVATION_PLAN["returned"]),
        ("cancelled", RESERVATION_PLAN["cancelled"]),
        ("expired", RESERVATION_PLAN["expired"]),
    ):
        for _ in range(amount):
            copy = rng.choice(copies)
            user = rng.choice(customers)
            reserved_at = now - timedelta(days=rng.randint(20, 400), hours=rng.randint(0, 23))

            if kind == "returned":
                expires_at = reserved_at + timedelta(days=14)
                reservations.append(
                    models.Reservation(
                        user_id=user.id,
                        physical_book_id=copy.id,
                        reserved_at=reserved_at,
                        expires_at=expires_at,
                        picked_up=True,
                        returned_at=reserved_at + timedelta(days=rng.randint(3, 25)),
                    )
                )
            elif kind == "cancelled":
                expires_at = reserved_at + timedelta(days=7)
                reservations.append(
                    models.Reservation(
                        user_id=user.id,
                        physical_book_id=copy.id,
                        reserved_at=reserved_at,
                        expires_at=expires_at,
                        picked_up=False,
                        cancelled_at=reserved_at + timedelta(days=rng.randint(1, 5)),
                    )
                )
            else:  # expired: nunca la retiraron y el vencimiento la cerró
                expires_at = reserved_at + timedelta(days=3)
                reservations.append(
                    models.Reservation(
                        user_id=user.id,
                        physical_book_id=copy.id,
                        reserved_at=reserved_at,
                        expires_at=expires_at,
                        picked_up=False,
                        cancelled_at=expires_at,
                    )
                )

    # Ahora las abiertas: un ejemplar por reserva, y el ejemplar cambia de estado.
    for kind, amount in (
        ("loaned", RESERVATION_PLAN["loaned"]),
        ("reserved", RESERVATION_PLAN["reserved"]),
    ):
        for _ in range(amount):
            copy = take_free()
            if copy is None:
                break
            user = rng.choice(customers)

            if kind == "loaned":
                reserved_at = now - timedelta(days=rng.randint(2, 25))
                # Algunas quedan en mora (vencidas y sin devolver): es lo que el
                # bibliotecario tiene que ver en su panel.
                expires_at = now + timedelta(days=rng.randint(-6, 18))
                copy.status = models.PhysicalBookStatus.loaned
                picked_up = True
            else:
                reserved_at = now - timedelta(days=rng.randint(0, 4))
                expires_at = now + timedelta(days=rng.randint(1, 7))
                copy.status = models.PhysicalBookStatus.reserved
                picked_up = False

            reservations.append(
                models.Reservation(
                    user_id=user.id,
                    physical_book_id=copy.id,
                    reserved_at=reserved_at,
                    expires_at=expires_at,
                    picked_up=picked_up,
                )
            )

    # `ana@bookup.example` es la lectora que documenta el README: se le garantiza una
    # reserva de cada estado para que «Mis reservas» muestre el ciclo completo sin
    # depender de la suerte del RNG.
    ana = customers[0]
    ana_reserved = take_free()
    if ana_reserved is not None:
        ana_reserved.status = models.PhysicalBookStatus.reserved
        reservations.append(
            models.Reservation(
                user_id=ana.id,
                physical_book_id=ana_reserved.id,
                reserved_at=now - timedelta(days=1),
                expires_at=now + timedelta(days=5),
                picked_up=False,
            )
        )
    ana_loaned = take_free()
    if ana_loaned is not None:
        ana_loaned.status = models.PhysicalBookStatus.loaned
        reservations.append(
            models.Reservation(
                user_id=ana.id,
                physical_book_id=ana_loaned.id,
                reserved_at=now - timedelta(days=9),
                expires_at=now + timedelta(days=12),
                picked_up=True,
            )
        )
    ana_history = rng.sample(copies, 2)
    reservations.append(
        models.Reservation(
            user_id=ana.id,
            physical_book_id=ana_history[0].id,
            reserved_at=now - timedelta(days=120),
            expires_at=now - timedelta(days=106),
            picked_up=True,
            returned_at=now - timedelta(days=110),
        )
    )
    reservations.append(
        models.Reservation(
            user_id=ana.id,
            physical_book_id=ana_history[1].id,
            reserved_at=now - timedelta(days=60),
            expires_at=now - timedelta(days=53),
            picked_up=False,
            cancelled_at=now - timedelta(days=58),
        )
    )

    # Unos pocos extraviados, siempre sobre ejemplares sin reserva abierta: `lost` cierra
    # la reserva viva si la hubiera, y eso es trabajo del service, no del seed.
    for _ in range(8):
        copy = take_free()
        if copy is None:
            break
        copy.status = models.PhysicalBookStatus.lost

    db.add_all(reservations)
    db.flush()
    return reservations


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(models.Library).count() > 0:
            print("Data already present, skipping seed.")
            return

        rng = random.Random(RANDOM_SEED)

        libraries, genres, books = _build_catalog(db)
        copies = _build_copies(db, rng, libraries, books)
        customers = _build_users(db, libraries)
        # Las sedes del README: ahí se concentran las reservas vivas de la demo.
        demo_library_ids = {libraries[key].id for key in ("central", "norte", "sur")}
        reservations = _build_reservations(db, rng, customers, copies, demo_library_ids)

        db.commit()

        open_reservations = sum(1 for r in reservations if r.is_open)
        print(
            "Sample data loaded:\n"
            f"  {len(libraries)} sedes\n"
            f"  {len(AUTHORS)} autores, {len(genres)} géneros, {len(books)} libros\n"
            f"  {len(copies)} ejemplares\n"
            f"  {len(LIBRARIANS) + 2} usuarios de staff, {len(customers)} lectores\n"
            f"  {len(reservations)} reservas ({open_reservations} abiertas)\n"
            f"Seeded users share the password {SEED_PASSWORD!r}."
        )
    finally:
        db.close()


if __name__ == "__main__":
    seed()
