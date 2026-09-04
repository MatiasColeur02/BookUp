import bcrypt

from app.persistence.models import User


def test_create_user(client):
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


def test_get_user(client):
    created = client.post(
        "/users", json={"email": "get@example.com", "password": "secret123", "name": "Get"}
    ).json()

    response = client.get(f"/users/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


def test_get_user_not_found(client):
    response = client.get("/users/999")
    assert response.status_code == 404


def test_list_users(client):
    client.post("/users", json={"email": "one@example.com", "password": "secret123", "name": "One"})
    client.post("/users", json={"email": "two@example.com", "password": "secret123", "name": "Two"})

    response = client.get("/users")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_patch_user_updates_name_and_language(client):
    created = client.post(
        "/users", json={"email": "patch@example.com", "password": "secret123", "name": "Patchy"}
    ).json()

    response = client.patch(f"/users/{created['id']}", json={"name": "Patched", "language": "en"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Patched"
    assert body["language"] == "en"
    assert body["email"] == "patch@example.com"


def test_patch_user_updates_password(client, db_session):
    created = client.post(
        "/users", json={"email": "pw@example.com", "password": "secret123", "name": "Pw"}
    ).json()

    response = client.patch(f"/users/{created['id']}", json={"password": "newsecret123"})
    assert response.status_code == 200

    user = db_session.query(User).filter_by(id=created["id"]).first()
    assert bcrypt.checkpw(b"newsecret123", user.password_hash.encode("utf-8"))


def test_patch_user_not_found(client):
    response = client.patch("/users/999", json={"name": "Nobody"})
    assert response.status_code == 404


def test_delete_user(client):
    created = client.post(
        "/users", json={"email": "del@example.com", "password": "secret123", "name": "Del"}
    ).json()

    response = client.delete(f"/users/{created['id']}")
    assert response.status_code == 204

    assert client.get(f"/users/{created['id']}").status_code == 404


def test_delete_user_not_found(client):
    response = client.delete("/users/999")
    assert response.status_code == 404
