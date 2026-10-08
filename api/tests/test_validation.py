"""Entradas hostiles: textos larguísimos, intentos de inyección y valores fuera de rango.

Lo que se prueba acá es que la API conteste **422** y no 500. La diferencia importa: un
500 significa que el valor llegó hasta la capa de datos (un ítem de DynamoDB admite 400 KB,
y un texto de megabytes se pasa), y en el camino ya consumió una escritura. El tope vive en
el esquema Pydantic, que es justamente lo que se busca.
"""

from app.persistence.entities import UserRole

ISBN = "9780306406157"

# Payloads clásicos de inyección SQL. No hay ninguno que pueda funcionar —no hay SQL: los
# datos van a DynamoDB como valores tipados y el texto libre a `multi_match`, nunca a
# `query_string`— pero el test deja constancia y avisa si alguien arma una consulta con texto
# del usuario.
SQL_INJECTION_PAYLOADS = [
    "'; DROP TABLE books; --",
    "' OR '1'='1",
    "1; DELETE FROM users WHERE 't'='t'",
    "%' UNION SELECT password_hash FROM users --",
]


def test_a_name_longer_than_the_column_is_a_422_not_a_500(client, sysadmin_headers):
    response = client.post(
        "/libraries",
        json={"name": "A" * 5_000, "address": "Calle 1", "state": "BA", "city": "La Plata"},
        headers=sysadmin_headers,
    )
    assert response.status_code == 422


def test_every_library_text_field_is_bounded(client, sysadmin_headers):
    base = {"name": "Sede", "address": "Calle 1", "state": "BA", "city": "La Plata"}
    for field, over in (
        ("name", 151),
        ("address", 256),
        ("state", 101),
        ("city", 101),
        ("hours", 256),
        ("phone", 51),
        ("email", 256),
        ("website", 256),
    ):
        response = client.post(
            "/libraries", json={**base, field: "x" * over}, headers=sysadmin_headers
        )
        assert response.status_code == 422, f"{field} aceptó {over} caracteres"


def test_blank_and_whitespace_only_names_are_rejected(client, sysadmin_headers):
    for blank in ("", "   ", "\n\t"):
        response = client.post(
            "/libraries",
            json={"name": blank, "address": "Calle 1", "state": "BA", "city": "La Plata"},
            headers=sysadmin_headers,
        )
        assert response.status_code == 422, f"aceptó un nombre en blanco: {blank!r}"


def test_text_fields_are_trimmed(client, sysadmin_headers):
    """Un nombre con espacios al costado se guarda limpio: si no, «Sede» y « Sede » conviven."""
    response = client.post(
        "/libraries",
        json={"name": "  Sede Norte  ", "address": " Calle 1 ", "state": "BA", "city": "Salta"},
        headers=sysadmin_headers,
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Sede Norte"
    assert response.json()["address"] == "Calle 1"


def test_optional_library_fields_still_accept_empty_strings(client, sysadmin_headers):
    """El frontend manda "" para vaciar un opcional: el tope no puede romper eso."""
    response = client.post(
        "/libraries",
        json={
            "name": "Sede Sur",
            "address": "Calle 2",
            "state": "BA",
            "city": "Quilmes",
            "hours": "",
            "phone": "",
        },
        headers=sysadmin_headers,
    )
    assert response.status_code == 201


def test_author_and_genre_names_are_bounded(client, sysadmin_headers):
    assert (
        client.post("/authors", json={"name": "A" * 201}, headers=sysadmin_headers).status_code
        == 422
    )
    assert (
        client.post("/genres", json={"name": "G" * 101}, headers=sysadmin_headers).status_code
        == 422
    )


def test_book_text_fields_and_page_count_are_bounded(client, sysadmin_headers):
    base = {"isbn": ISBN, "title": "Un libro", "language": "es"}
    too_long = {**base, "title": "T" * 256}
    assert client.post("/books", json=too_long, headers=sysadmin_headers).status_code == 422

    huge_synopsis = {**base, "synopsis": "s" * 5_001}
    assert client.post("/books", json=huge_synopsis, headers=sysadmin_headers).status_code == 422

    for pages in (0, -10, 10**9):
        payload = {**base, "pages": pages}
        assert (
            client.post("/books", json=payload, headers=sysadmin_headers).status_code == 422
        ), f"aceptó pages={pages}"


def test_password_over_the_bcrypt_limit_is_rejected(client):
    """bcrypt ignora todo lo que pase de 72 bytes: aceptarlo sería truncar en silencio."""
    response = client.post(
        "/users",
        json={"email": "largo@bookup.example", "password": "p" * 73, "name": "Largo"},
        headers={},
    )
    assert response.status_code == 422


def test_password_limit_counts_bytes_and_not_characters(client):
    # 40 caracteres, pero 120 bytes en UTF-8: el límite de bcrypt es en bytes.
    response = client.post(
        "/users",
        json={"email": "emoji@bookup.example", "password": "🔒" * 30, "name": "Emoji"},
    )
    assert response.status_code == 422


def test_user_name_and_language_are_bounded(client):
    assert (
        client.post(
            "/users",
            json={"email": "a@bookup.example", "password": "secret123", "name": "N" * 151},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/users",
            json={
                "email": "b@bookup.example",
                "password": "secret123",
                "name": "N",
                "language": "x" * 11,
            },
        ).status_code
        == 422
    )


def test_sql_injection_payloads_do_not_run_as_sql(client, make, sysadmin_headers):
    """No hay SQL ni intérprete de consultas: el texto se busca literalmente y no pasa nada."""
    make.book(ISBN, "Un libro")

    for payload in SQL_INJECTION_PAYLOADS:
        response = client.get("/books", params={"q": payload})
        assert response.status_code == 200
        # Se buscó el texto tal cual, así que no matchea nada.
        assert response.json()["items"] == []

    # Y lo importante: las tablas siguen ahí con sus datos.
    assert client.get(f"/books/{ISBN}").status_code == 200


def test_sql_injection_in_a_stored_name_is_stored_as_text(client, sysadmin_headers):
    """Guardar `'; DROP TABLE ...` es legítimo: es un nombre feo, no una sentencia."""
    payload = "Robert'); DROP TABLE authors; --"
    created = client.post("/authors", json={"name": payload}, headers=sysadmin_headers)
    assert created.status_code == 201
    assert created.json()["name"] == payload
    # La tabla sigue existiendo y el autor está adentro.
    assert client.get("/authors").status_code == 200


def test_search_query_length_is_bounded(client):
    assert client.get("/books", params={"q": "x" * 201}).status_code == 422
    assert client.get("/books/search", params={"q": "x" * 201}).status_code == 422


def test_the_number_of_repeated_filters_is_bounded(client):
    """`?genre_id=1&genre_id=2&…` mil veces arma un IN gigante y una entrada de cache nueva."""
    response = client.get("/books", params=[("genre_id", str(n)) for n in range(50)])
    assert response.status_code == 422


def test_city_filter_values_are_bounded(client):
    assert client.get("/books", params={"city": "c" * 101}).status_code == 422


def test_a_wildcard_search_does_not_dump_the_catalog(client, make):
    """`%` es un carácter más, no un comodín: buscar «%» no devuelve todo el catálogo."""
    make.book(ISBN, "Un libro")

    response = client.get("/books", params={"q": "%"})
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_reservation_cannot_be_parked_for_years(client, make, make_user, auth_headers):
    """Un `expires_at` lejano retiene el ejemplar: futuro no alcanza como validación."""
    make.library("Sede", city="La Plata")
    make.book(ISBN, "Un libro")
    headers = auth_headers(make_user(UserRole.customer))

    # Ni siquiera hace falta que el ejemplar exista: el 422 sale de la validación del
    # payload, antes de mirar la base.
    response = client.post(
        "/reservations",
        json={"physical_book_id": 1, "expires_at": "9999-12-31T00:00:00Z"},
        headers=headers,
    )
    assert response.status_code == 422


def test_a_request_body_over_the_limit_is_rejected_with_413(client, sysadmin_headers):
    """Se corta por `Content-Length`, antes de bufferear el cuerpo entero en memoria."""
    response = client.post(
        "/books",
        content=b'{"padding": "' + b"x" * (1024 * 1024 + 10) + b'"}',
        headers={**sysadmin_headers, "content-type": "application/json"},
    )
    assert response.status_code == 413
