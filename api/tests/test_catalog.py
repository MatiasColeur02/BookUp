import pytest

from app.persistence.repositories import PhysicalBookRepository, ReservationRepository


@pytest.fixture()
def sample_catalog(make, sync_search):
    library_a = make.library("Central", city="CABA")
    library_b = make.library("Norte", city="Rosario")

    author = make.author("Jorge Luis Borges")
    genre = make.genre("Ficción")

    book = make.book(
        "9788420633107",
        "Ficciones",
        authors=[author],
        genres=[genre],
        synopsis="Cuentos fantásticos y filosóficos.",
    )

    make.copy(book.isbn, library_a)
    make.copy(book.isbn, library_b)
    sync_search()  # el indexador, en producción, un instante después de cada escritura
    return book, library_a, library_b


def test_list_books_returns_page_with_total(client, sample_catalog):
    response = client.get("/books")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert [b["isbn"] for b in body["items"]] == ["9788420633107"]


def test_list_books_offset_past_the_end_is_empty(client, sample_catalog):
    response = client.get("/books", params={"limit": 5, "offset": 5})
    assert response.status_code == 200
    body = response.json()
    # El total sigue siendo el del catálogo entero, aunque la página venga vacía.
    assert body["items"] == []
    assert body["total"] == 1


def test_list_books_rejects_invalid_limit(client, sample_catalog):
    assert client.get("/books", params={"limit": 0}).status_code == 422
    assert client.get("/books", params={"limit": 500}).status_code == 422
    assert client.get("/books", params={"offset": -1}).status_code == 422


def test_list_books_filters_by_text(client, sample_catalog):
    assert client.get("/books", params={"q": "Borges"}).json()["total"] == 1
    assert client.get("/books", params={"q": "nomatch"}).json()["total"] == 0


def test_list_books_filters_by_author_and_genre(client, sample_catalog):
    book, _, _ = sample_catalog
    author_id = book.authors[0].id
    genre_id = book.genres[0].id

    assert client.get("/books", params={"author_id": author_id}).json()["total"] == 1
    assert client.get("/books", params={"genre_id": genre_id}).json()["total"] == 1
    assert client.get("/books", params={"author_id": 9999}).json()["total"] == 0


def test_list_books_repeated_filter_is_an_or(client, sample_catalog):
    book, _, _ = sample_catalog
    genre_id = book.genres[0].id
    # Uno de los dos existe: el libro tiene que aparecer igual.
    response = client.get("/books", params=[("genre_id", genre_id), ("genre_id", 9999)])
    assert response.json()["total"] == 1


def test_list_books_different_filters_are_an_and(client, sample_catalog):
    book, _, _ = sample_catalog
    # El género es suyo, pero el autor no: no matchea.
    response = client.get(
        "/books", params=[("genre_id", book.genres[0].id), ("author_id", 9999)]
    )
    assert response.json()["total"] == 0


def test_list_books_filters_by_city_with_available_stock(client, sample_catalog):
    book, library_a, _ = sample_catalog
    assert client.get("/books", params={"city": library_a.city}).json()["total"] == 1
    assert client.get("/books", params={"city": "Narnia"}).json()["total"] == 0


def test_city_filter_ignores_copies_that_are_not_available(
    client, sample_catalog, make, db, sync_search
):
    book, library_a, library_b = sample_catalog
    # "En esta ciudad" es "reservable hoy": un ejemplar prestado no cuenta.
    for copy in PhysicalBookRepository(db).list_all(library_id=library_a.id):
        reservation = make.reservation(copy)
        ReservationRepository(db).mark_picked_up(reservation.id)
    sync_search()

    assert client.get("/books", params={"city": library_a.city}).json()["total"] == 0
    assert client.get("/books", params={"city": library_b.city}).json()["total"] == 1


def test_list_cities_returns_cities_with_stock(client, sample_catalog):
    response = client.get("/books/cities")
    assert response.status_code == 200
    assert response.json() == ["CABA", "Rosario"]


def test_filters_combine_with_pagination(client, sample_catalog):
    response = client.get("/books", params={"q": "Ficciones", "limit": 1, "offset": 1})
    body = response.json()
    # El total es el del filtro, no el de la página.
    assert body["total"] == 1
    assert body["items"] == []


def test_search_books_by_title(client, sample_catalog):
    book, _, _ = sample_catalog
    response = client.get("/books/search", params={"q": "Ficciones"})
    assert response.status_code == 200
    isbns = [b["isbn"] for b in response.json()]
    assert book.isbn in isbns


def test_search_books_by_author(client, sample_catalog):
    response = client.get("/books/search", params={"q": "Borges"})
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_search_books_no_match(client, sample_catalog):
    response = client.get("/books/search", params={"q": "nomatch"})
    assert response.status_code == 200
    assert response.json() == []


def test_get_book(client, sample_catalog):
    book, _, _ = sample_catalog
    response = client.get(f"/books/{book.isbn}")
    assert response.status_code == 200
    body = response.json()
    assert body["isbn"] == book.isbn
    assert body["authors"][0]["name"] == "Jorge Luis Borges"
    assert body["genres"][0]["name"] == "Ficción"


def test_get_book_not_found(client):
    response = client.get("/books/0000000000000")
    assert response.status_code == 404


def test_get_availability(client, sample_catalog):
    book, library_a, library_b = sample_catalog
    response = client.get(f"/books/{book.isbn}/availability")
    assert response.status_code == 200
    body = response.json()
    assert body["book"]["isbn"] == book.isbn
    assert len(body["libraries"]) == 2
    for entry in body["libraries"]:
        assert entry["available_copies"] == 1
        assert entry["physical_book_id"] is not None


def test_get_availability_book_not_found(client):
    response = client.get("/books/0000000000000/availability")
    assert response.status_code == 404
