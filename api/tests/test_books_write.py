import pytest

from app.persistence.models import Author, Genre, Library, PhysicalBook, UserRole

ISBN = "9780307474728"


@pytest.fixture()
def author_and_genre(db_session):
    author = Author(name="Gabriel García Márquez")
    genre = Genre(name="Ficción")
    db_session.add_all([author, genre])
    db_session.commit()
    db_session.refresh(author)
    db_session.refresh(genre)
    return author, genre


def _payload(**overrides) -> dict:
    payload = {"isbn": ISBN, "title": "Cien años de soledad", "language": "es"}
    payload.update(overrides)
    return payload


def test_create_book(client, sysadmin_headers, author_and_genre):
    author, genre = author_and_genre
    response = client.post(
        "/books",
        json=_payload(pages=471, author_ids=[author.id], genre_ids=[genre.id]),
        headers=sysadmin_headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["isbn"] == ISBN
    assert body["pages"] == 471
    assert [a["name"] for a in body["authors"]] == ["Gabriel García Márquez"]
    assert [g["name"] for g in body["genres"]] == ["Ficción"]


def test_create_book_requires_staff(client, make_user, auth_headers):
    assert client.post("/books", json=_payload()).status_code == 401
    response = client.post("/books", json=_payload(), headers=auth_headers(make_user()))
    assert response.status_code == 403


def test_librarian_can_create_a_book(client, make_user, auth_headers):
    headers = auth_headers(make_user(UserRole.librarian))
    assert client.post("/books", json=_payload(), headers=headers).status_code == 201


def test_create_book_duplicate_isbn_conflicts(client, sysadmin_headers):
    assert client.post("/books", json=_payload(), headers=sysadmin_headers).status_code == 201
    response = client.post("/books", json=_payload(), headers=sysadmin_headers)
    assert response.status_code == 409


@pytest.mark.parametrize(
    "isbn",
    [
        "978030747472",  # 12 digits
        "97803074747289",  # 14 digits
        "978030747472X",  # not all digits
        "9780307474727",  # wrong check digit
    ],
)
def test_create_book_rejects_malformed_isbn(client, sysadmin_headers, isbn):
    response = client.post("/books", json=_payload(isbn=isbn), headers=sysadmin_headers)
    assert response.status_code == 422


def test_create_book_with_unknown_author(client, sysadmin_headers):
    response = client.post(
        "/books", json=_payload(author_ids=[9999]), headers=sysadmin_headers
    )
    assert response.status_code == 404


def test_create_book_with_unknown_genre(client, sysadmin_headers):
    response = client.post("/books", json=_payload(genre_ids=[9999]), headers=sysadmin_headers)
    assert response.status_code == 404


def test_search_route_still_wins_over_the_isbn_route(client, sysadmin_headers):
    client.post("/books", json=_payload(), headers=sysadmin_headers)

    response = client.get("/books/search", params={"q": "Cien"})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_update_book_partial(client, sysadmin_headers):
    client.post("/books", json=_payload(pages=471), headers=sysadmin_headers)

    response = client.patch(
        f"/books/{ISBN}", json={"title": "Cien años de soledad (ed. conmemorativa)"},
        headers=sysadmin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Cien años de soledad (ed. conmemorativa)"
    assert body["pages"] == 471


def test_update_book_replaces_the_author_list(client, sysadmin_headers, author_and_genre, db_session):
    author, _ = author_and_genre
    other = Author(name="Otro Autor")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    client.post("/books", json=_payload(author_ids=[author.id]), headers=sysadmin_headers)

    response = client.patch(
        f"/books/{ISBN}", json={"author_ids": [other.id]}, headers=sysadmin_headers
    )
    assert response.status_code == 200
    assert [a["name"] for a in response.json()["authors"]] == ["Otro Autor"]


def test_update_book_can_clear_the_author_list(client, sysadmin_headers, author_and_genre):
    author, _ = author_and_genre
    client.post("/books", json=_payload(author_ids=[author.id]), headers=sysadmin_headers)

    response = client.patch(f"/books/{ISBN}", json={"author_ids": []}, headers=sysadmin_headers)
    assert response.status_code == 200
    assert response.json()["authors"] == []


def test_update_book_not_found(client, sysadmin_headers):
    response = client.patch("/books/9780000000001", json={"title": "X"}, headers=sysadmin_headers)
    assert response.status_code == 404


def test_delete_book(client, sysadmin_headers):
    client.post("/books", json=_payload(), headers=sysadmin_headers)

    response = client.delete(f"/books/{ISBN}", headers=sysadmin_headers)
    assert response.status_code == 204
    assert client.get(f"/books/{ISBN}").status_code == 404


def test_delete_book_not_found(client, sysadmin_headers):
    assert client.delete("/books/9780000000001", headers=sysadmin_headers).status_code == 404


def test_delete_book_conflicts_with_physical_copies(client, sysadmin_headers, db_session):
    client.post("/books", json=_payload(), headers=sysadmin_headers)

    library = Library(name="Central", address="Calle 1", state="BA", city="CABA")
    db_session.add(library)
    db_session.flush()
    db_session.add(PhysicalBook(isbn=ISBN, library_id=library.id))
    db_session.commit()

    response = client.delete(f"/books/{ISBN}", headers=sysadmin_headers)
    assert response.status_code == 409
