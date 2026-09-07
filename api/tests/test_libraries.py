from app.persistence.models import Book, PhysicalBook


def test_create_library(client):
    payload = {
        "name": "Biblioteca Central",
        "address": "Av. Corrientes 1234",
        "state": "Buenos Aires",
        "city": "Buenos Aires",
        "hours": "9 a 18",
        "phone": "1234-5678",
        "email": "central@bookup.example",
        "website": "https://bookup.example/central",
    }
    response = client.post("/libraries", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == payload["name"]
    assert body["city"] == payload["city"]
    assert "id" in body


def test_create_library_optional_fields_default_to_none(client):
    payload = {
        "name": "Biblioteca del Norte",
        "address": "San Martín 500",
        "state": "Santa Fe",
        "city": "Rosario",
    }
    response = client.post("/libraries", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["hours"] is None
    assert body["phone"] is None
    assert body["email"] is None
    assert body["website"] is None


def test_list_libraries(client):
    client.post(
        "/libraries",
        json={"name": "Central", "address": "Calle 1", "state": "BA", "city": "CABA"},
    )
    client.post(
        "/libraries",
        json={"name": "Norte", "address": "Calle 2", "state": "SF", "city": "Rosario"},
    )

    response = client.get("/libraries")
    assert response.status_code == 200
    assert len(response.json()) == 2


def _create_library(client, **overrides) -> dict:
    payload = {"name": "Central", "address": "Calle 1", "state": "BA", "city": "CABA"}
    payload.update(overrides)
    return client.post("/libraries", json=payload).json()


def test_get_library(client):
    created = _create_library(client)

    response = client.get(f"/libraries/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_get_library_not_found(client):
    response = client.get("/libraries/9999")
    assert response.status_code == 404


def test_update_library_partial(client):
    created = _create_library(client, phone="1234-5678")

    response = client.patch(f"/libraries/{created['id']}", json={"name": "Central renombrada"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Central renombrada"
    # Untouched fields keep their previous value.
    assert body["address"] == created["address"]
    assert body["phone"] == "1234-5678"


def test_update_library_not_found(client):
    response = client.patch("/libraries/9999", json={"name": "Fantasma"})
    assert response.status_code == 404


def test_delete_library(client):
    created = _create_library(client)

    response = client.delete(f"/libraries/{created['id']}")
    assert response.status_code == 204
    assert client.get(f"/libraries/{created['id']}").status_code == 404


def test_delete_library_not_found(client):
    response = client.delete("/libraries/9999")
    assert response.status_code == 404


def test_delete_library_conflicts_with_physical_books(client, db_session):
    created = _create_library(client)

    book = Book(isbn="9780307474728", title="Cien años de soledad", language="es")
    db_session.add(book)
    db_session.flush()
    db_session.add(PhysicalBook(isbn=book.isbn, library_id=created["id"]))
    db_session.commit()

    response = client.delete(f"/libraries/{created['id']}")
    assert response.status_code == 409
    assert client.get(f"/libraries/{created['id']}").status_code == 200
