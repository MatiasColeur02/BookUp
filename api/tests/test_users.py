import bcrypt

from app.persistence.models import Library, User, UserRole


def test_create_user_is_public(client):
    response = client.post(
        "/users", json={"email": "ana@example.com", "password": "secret123", "name": "Ana"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ana@example.com"
    assert body["name"] == "Ana"
    assert body["language"] == "es"
    assert body["role"] == "customer"
    assert body["library_id"] is None
    assert "password" not in body
    assert "password_hash" not in body


def test_create_user_cannot_choose_its_role(client):
    response = client.post(
        "/users",
        json={
            "email": "wannabe@example.com",
            "password": "secret123",
            "name": "Wannabe",
            "role": "sysadmin",
        },
    )
    # `role` is not part of UserCreate, so it is ignored: the user is a customer.
    assert response.status_code == 201
    assert response.json()["role"] == "customer"


def test_create_user_hashes_password(client, db_session):
    client.post(
        "/users", json={"email": "hash@example.com", "password": "secret123", "name": "Hash"}
    )
    user = db_session.query(User).filter_by(email="hash@example.com").first()
    assert user.password_hash != "secret123"
    assert bcrypt.checkpw(b"secret123", user.password_hash.encode("utf-8"))


def test_create_user_duplicate_email_conflicts(client):
    payload = {"email": "dup@example.com", "password": "secret123", "name": "Dup"}
    client.post("/users", json=payload)
    response = client.post("/users", json=payload)
    assert response.status_code == 409


def test_create_user_rejects_short_password(client):
    response = client.post(
        "/users", json={"email": "short@example.com", "password": "short", "name": "Short"}
    )
    assert response.status_code == 422


def test_create_staff_user(client, sysadmin_headers, db_session):
    library = Library(name="Central", address="Calle 1", state="BA", city="CABA")
    db_session.add(library)
    db_session.commit()

    response = client.post(
        "/users/staff",
        json={
            "email": "bibliotecario@example.com",
            "password": "secret123",
            "name": "Biblio",
            "role": "librarian",
            "library_id": library.id,
        },
        headers=sysadmin_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "librarian"
    assert body["library_id"] == library.id


def test_create_staff_user_forbidden_for_customers(client, make_user, auth_headers):
    response = client.post(
        "/users/staff",
        json={
            "email": "sneaky@example.com",
            "password": "secret123",
            "name": "Sneaky",
            "role": "sysadmin",
        },
        headers=auth_headers(make_user()),
    )
    assert response.status_code == 403


def test_create_staff_user_requires_a_token(client):
    response = client.post(
        "/users/staff",
        json={
            "email": "sneaky@example.com",
            "password": "secret123",
            "name": "Sneaky",
            "role": "sysadmin",
        },
    )
    assert response.status_code == 401


def test_create_staff_user_rejects_library_id_on_a_non_librarian(client, sysadmin_headers, db_session):
    library = Library(name="Central", address="Calle 1", state="BA", city="CABA")
    db_session.add(library)
    db_session.commit()

    response = client.post(
        "/users/staff",
        json={
            "email": "confused@example.com",
            "password": "secret123",
            "name": "Confused",
            "role": "sysadmin",
            "library_id": library.id,
        },
        headers=sysadmin_headers,
    )
    assert response.status_code == 409


def test_create_staff_user_with_unknown_library(client, sysadmin_headers):
    response = client.post(
        "/users/staff",
        json={
            "email": "ghost@example.com",
            "password": "secret123",
            "name": "Ghost",
            "role": "librarian",
            "library_id": 9999,
        },
        headers=sysadmin_headers,
    )
    assert response.status_code == 404


def test_list_users_requires_sysadmin(client, make_user, auth_headers, sysadmin_headers):
    make_user()

    assert client.get("/users").status_code == 401
    assert client.get("/users", headers=auth_headers(make_user())).status_code == 403

    response = client.get("/users", headers=sysadmin_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_get_own_user(client, make_user, auth_headers):
    user = make_user()
    response = client.get(f"/users/{user.id}", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json()["id"] == user.id


def test_get_another_user_is_forbidden(client, make_user, auth_headers):
    user = make_user()
    other = make_user()
    response = client.get(f"/users/{other.id}", headers=auth_headers(user))
    assert response.status_code == 403


def test_sysadmin_can_get_any_user(client, make_user, sysadmin_headers):
    user = make_user()
    response = client.get(f"/users/{user.id}", headers=sysadmin_headers)
    assert response.status_code == 200


def test_get_user_not_found(client, sysadmin_headers):
    response = client.get("/users/9999", headers=sysadmin_headers)
    assert response.status_code == 404


def test_patch_user_updates_name_and_language(client, make_user, auth_headers):
    user = make_user()
    response = client.patch(
        f"/users/{user.id}", json={"name": "Patched", "language": "en"}, headers=auth_headers(user)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Patched"
    assert body["language"] == "en"
    assert body["email"] == user.email


def test_patch_user_updates_password(client, make_user, auth_headers, db_session):
    user = make_user()
    response = client.patch(
        f"/users/{user.id}", json={"password": "newsecret123"}, headers=auth_headers(user)
    )
    assert response.status_code == 200

    db_session.expire_all()
    refreshed = db_session.get(User, user.id)
    assert bcrypt.checkpw(b"newsecret123", refreshed.password_hash.encode("utf-8"))


def test_customer_cannot_promote_themselves(client, make_user, auth_headers):
    user = make_user()
    response = client.patch(
        f"/users/{user.id}", json={"role": "sysadmin"}, headers=auth_headers(user)
    )
    assert response.status_code == 403


def test_sysadmin_can_assign_a_librarian_to_a_library(
    client, make_user, sysadmin_headers, db_session
):
    library = Library(name="Central", address="Calle 1", state="BA", city="CABA")
    db_session.add(library)
    db_session.commit()
    user = make_user()

    response = client.patch(
        f"/users/{user.id}",
        json={"role": "librarian", "library_id": library.id},
        headers=sysadmin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "librarian"
    assert body["library_id"] == library.id


def test_demoting_a_librarian_clears_their_library(
    client, make_user, sysadmin_headers, db_session
):
    library = Library(name="Central", address="Calle 1", state="BA", city="CABA")
    db_session.add(library)
    db_session.commit()
    librarian = make_user(UserRole.librarian, library_id=library.id)

    response = client.patch(
        f"/users/{librarian.id}", json={"role": "customer"}, headers=sysadmin_headers
    )
    assert response.status_code == 200
    assert response.json()["library_id"] is None


def test_patch_user_not_found(client, sysadmin_headers):
    response = client.patch("/users/9999", json={"name": "Nobody"}, headers=sysadmin_headers)
    assert response.status_code == 404


def test_delete_own_user(client, make_user, auth_headers, sysadmin_headers):
    user = make_user()
    response = client.delete(f"/users/{user.id}", headers=auth_headers(user))
    assert response.status_code == 204
    assert client.get(f"/users/{user.id}", headers=sysadmin_headers).status_code == 404


def test_delete_another_user_is_forbidden(client, make_user, auth_headers):
    user = make_user()
    other = make_user()
    response = client.delete(f"/users/{other.id}", headers=auth_headers(user))
    assert response.status_code == 403


def test_delete_user_not_found(client, sysadmin_headers):
    response = client.delete("/users/9999", headers=sysadmin_headers)
    assert response.status_code == 404
