from app.persistence.models import Book, Genre, UserRole


def test_list_genres_is_public(client, db_session):
    db_session.add_all([Genre(name="Ficción"), Genre(name="Ensayo")])
    db_session.commit()

    response = client.get("/genres")
    assert response.status_code == 200
    assert [g["name"] for g in response.json()] == ["Ensayo", "Ficción"]


def test_create_genre(client, make_user, auth_headers):
    headers = auth_headers(make_user(UserRole.librarian))
    response = client.post("/genres", json={"name": "Ficción"}, headers=headers)

    assert response.status_code == 201
    assert response.json()["name"] == "Ficción"


def test_create_genre_requires_staff(client, make_user, auth_headers):
    assert client.post("/genres", json={"name": "Ficción"}).status_code == 401
    response = client.post("/genres", json={"name": "Ficción"}, headers=auth_headers(make_user()))
    assert response.status_code == 403


def test_create_genre_duplicate_name_conflicts(client, sysadmin_headers):
    assert client.post("/genres", json={"name": "Ficción"}, headers=sysadmin_headers).status_code == 201
    response = client.post("/genres", json={"name": "Ficción"}, headers=sysadmin_headers)
    assert response.status_code == 409


def test_get_genre(client, sysadmin_headers):
    created = client.post("/genres", json={"name": "Ficción"}, headers=sysadmin_headers).json()

    response = client.get(f"/genres/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_get_genre_not_found(client):
    assert client.get("/genres/9999").status_code == 404


def test_update_genre(client, sysadmin_headers):
    created = client.post("/genres", json={"name": "Ficcion"}, headers=sysadmin_headers).json()

    response = client.patch(
        f"/genres/{created['id']}", json={"name": "Ficción"}, headers=sysadmin_headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Ficción"


def test_update_genre_to_an_existing_name_conflicts(client, sysadmin_headers):
    client.post("/genres", json={"name": "Ficción"}, headers=sysadmin_headers)
    other = client.post("/genres", json={"name": "Ensayo"}, headers=sysadmin_headers).json()

    response = client.patch(
        f"/genres/{other['id']}", json={"name": "Ficción"}, headers=sysadmin_headers
    )
    assert response.status_code == 409


def test_update_genre_keeping_its_own_name(client, sysadmin_headers):
    created = client.post("/genres", json={"name": "Ficción"}, headers=sysadmin_headers).json()

    response = client.patch(
        f"/genres/{created['id']}", json={"name": "Ficción"}, headers=sysadmin_headers
    )
    assert response.status_code == 200


def test_delete_genre(client, sysadmin_headers):
    created = client.post("/genres", json={"name": "Ficción"}, headers=sysadmin_headers).json()

    response = client.delete(f"/genres/{created['id']}", headers=sysadmin_headers)
    assert response.status_code == 204
    assert client.get(f"/genres/{created['id']}").status_code == 404


def test_delete_genre_conflicts_when_linked_to_a_book(client, sysadmin_headers, db_session):
    genre = Genre(name="Ficción")
    db_session.add(genre)
    db_session.flush()
    db_session.add(Book(isbn="9788420633107", title="Ficciones", language="es", genres=[genre]))
    db_session.commit()

    response = client.delete(f"/genres/{genre.id}", headers=sysadmin_headers)
    assert response.status_code == 409
