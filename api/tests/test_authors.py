from app.persistence.models import Author, Book, UserRole


def test_list_authors_is_public(client, db_session):
    db_session.add_all([Author(name="Borges"), Author(name="Cortázar")])
    db_session.commit()

    response = client.get("/authors")
    assert response.status_code == 200
    assert [a["name"] for a in response.json()] == ["Borges", "Cortázar"]


def test_create_author(client, make_user, auth_headers):
    headers = auth_headers(make_user(UserRole.librarian))
    response = client.post("/authors", json={"name": "Jorge Luis Borges"}, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Jorge Luis Borges"
    assert "id" in body


def test_create_author_requires_staff(client, make_user, auth_headers):
    assert client.post("/authors", json={"name": "Anon"}).status_code == 401
    response = client.post("/authors", json={"name": "Anon"}, headers=auth_headers(make_user()))
    assert response.status_code == 403


def test_create_author_allows_homonyms(client, sysadmin_headers):
    first = client.post("/authors", json={"name": "Juan Pérez"}, headers=sysadmin_headers)
    second = client.post("/authors", json={"name": "Juan Pérez"}, headers=sysadmin_headers)

    # `Author.name` is not unique in the model: two people may share a name.
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_create_author_rejects_empty_name(client, sysadmin_headers):
    response = client.post("/authors", json={"name": ""}, headers=sysadmin_headers)
    assert response.status_code == 422


def test_get_author(client, sysadmin_headers):
    created = client.post(
        "/authors", json={"name": "Borges"}, headers=sysadmin_headers
    ).json()

    response = client.get(f"/authors/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_get_author_not_found(client):
    assert client.get("/authors/9999").status_code == 404


def test_update_author(client, sysadmin_headers):
    created = client.post("/authors", json={"name": "Borges"}, headers=sysadmin_headers).json()

    response = client.patch(
        f"/authors/{created['id']}", json={"name": "Jorge Luis Borges"}, headers=sysadmin_headers
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Jorge Luis Borges"


def test_update_author_not_found(client, sysadmin_headers):
    response = client.patch("/authors/9999", json={"name": "X"}, headers=sysadmin_headers)
    assert response.status_code == 404


def test_delete_author(client, sysadmin_headers):
    created = client.post("/authors", json={"name": "Borges"}, headers=sysadmin_headers).json()

    response = client.delete(f"/authors/{created['id']}", headers=sysadmin_headers)
    assert response.status_code == 204
    assert client.get(f"/authors/{created['id']}").status_code == 404


def test_delete_author_not_found(client, sysadmin_headers):
    assert client.delete("/authors/9999", headers=sysadmin_headers).status_code == 404


def test_delete_author_conflicts_when_linked_to_a_book(client, sysadmin_headers, db_session):
    author = Author(name="Borges")
    db_session.add(author)
    db_session.flush()
    db_session.add(
        Book(isbn="9788420633107", title="Ficciones", language="es", authors=[author])
    )
    db_session.commit()

    response = client.delete(f"/authors/{author.id}", headers=sysadmin_headers)
    assert response.status_code == 409
