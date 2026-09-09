"""Portadas de libros: firma, confirmación y baja.

La suite corre sin `S3_BUCKET`, así que por defecto la feature está apagada. Los tests
que ejercitan el flujo completo encienden el bucket por settings y reemplazan las tres
funciones que hablan con S3 (`presign_upload`, `exists`, `delete`): lo que se prueba acá
es la lógica del endpoint, no boto3.
"""

import pytest

from app import storage
from app.config import settings
from app.persistence.models import Book

ISBN = "9780306406157"


@pytest.fixture()
def book(db_session):
    book = Book(isbn=ISBN, title="Un libro", language="es")
    db_session.add(book)
    db_session.commit()
    return book


@pytest.fixture()
def s3(monkeypatch):
    """Enciende la feature y stubea S3. `uploaded` junta las keys borradas."""
    monkeypatch.setattr(settings, "s3_bucket", "test-bucket")
    monkeypatch.setattr(settings, "s3_endpoint_url", "")
    monkeypatch.setattr(settings, "s3_public_endpoint_url", "")
    monkeypatch.setattr(settings, "s3_public_base_url", "")

    deleted: list[str] = []
    monkeypatch.setattr(storage, "presign_upload", lambda key, content_type: f"https://s3/{key}")
    monkeypatch.setattr(storage, "exists", lambda key: True)
    monkeypatch.setattr(storage, "delete", lambda key: deleted.append(key) if key else None)
    return deleted


def test_cover_upload_is_503_without_bucket(client, book, sysadmin_headers, monkeypatch):
    # Apagar el bucket explícitamente y no confiar en el entorno: el contenedor de
    # `docker compose` sí trae `S3_BUCKET`, y ahí el test daría 200.
    monkeypatch.setattr(settings, "s3_bucket", "")
    response = client.post(
        f"/books/{ISBN}/cover-upload",
        json={"content_type": "image/png", "size": 100},
        headers=sysadmin_headers,
    )
    assert response.status_code == 503


def test_cover_upload_requires_staff(client, book, s3):
    assert (
        client.post(
            f"/books/{ISBN}/cover-upload", json={"content_type": "image/png", "size": 100}
        ).status_code
        == 401
    )


def test_cover_upload_returns_signed_url(client, book, s3, sysadmin_headers):
    response = client.post(
        f"/books/{ISBN}/cover-upload",
        json={"content_type": "image/png", "size": 100},
        headers=sysadmin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    # La key va bajo el prefijo del libro: es lo que después valida `PUT /cover`.
    assert body["key"].startswith(f"covers/{ISBN}/")
    assert body["key"].endswith(".png")
    assert body["upload_url"].endswith(body["key"])
    assert body["content_type"] == "image/png"


def test_cover_upload_rejects_unsupported_type(client, book, s3, sysadmin_headers):
    response = client.post(
        f"/books/{ISBN}/cover-upload",
        json={"content_type": "application/pdf", "size": 100},
        headers=sysadmin_headers,
    )
    assert response.status_code == 422


def test_cover_upload_rejects_oversized_file(client, book, s3, sysadmin_headers):
    response = client.post(
        f"/books/{ISBN}/cover-upload",
        json={"content_type": "image/png", "size": settings.cover_max_bytes + 1},
        headers=sysadmin_headers,
    )
    assert response.status_code == 422


def test_cover_upload_unknown_book_is_404(client, s3, sysadmin_headers):
    response = client.post(
        "/books/9999999999999/cover-upload",
        json={"content_type": "image/png", "size": 100},
        headers=sysadmin_headers,
    )
    assert response.status_code == 404


def test_attach_cover_sets_cover_url(client, book, s3, sysadmin_headers):
    key = f"covers/{ISBN}/abc.png"
    response = client.put(f"/books/{ISBN}/cover", json={"key": key}, headers=sysadmin_headers)
    assert response.status_code == 200
    assert response.json()["cover_url"].endswith(key)

    # Y el catálogo la devuelve: `cover_url` sale de `cover_key`, que no se expone.
    listed = client.get("/books").json()["items"][0]
    assert listed["cover_url"].endswith(key)
    assert "cover_key" not in listed


def test_attach_cover_rejects_key_of_another_book(client, book, s3, sysadmin_headers):
    response = client.put(
        f"/books/{ISBN}/cover", json={"key": "covers/9999999999999/x.png"}, headers=sysadmin_headers
    )
    assert response.status_code == 422


def test_attach_cover_rejects_missing_object(client, book, s3, sysadmin_headers, monkeypatch):
    # El PUT del browser falló: guardar la key dejaría el catálogo con una imagen rota.
    monkeypatch.setattr(storage, "exists", lambda key: False)
    response = client.put(
        f"/books/{ISBN}/cover", json={"key": f"covers/{ISBN}/x.png"}, headers=sysadmin_headers
    )
    assert response.status_code == 422


def test_replacing_a_cover_deletes_the_previous_object(client, book, s3, sysadmin_headers):
    first = f"covers/{ISBN}/first.png"
    second = f"covers/{ISBN}/second.png"
    client.put(f"/books/{ISBN}/cover", json={"key": first}, headers=sysadmin_headers)
    client.put(f"/books/{ISBN}/cover", json={"key": second}, headers=sysadmin_headers)
    assert s3 == [first]


def test_remove_cover_clears_the_column_and_the_object(client, book, s3, sysadmin_headers):
    key = f"covers/{ISBN}/abc.png"
    client.put(f"/books/{ISBN}/cover", json={"key": key}, headers=sysadmin_headers)

    response = client.delete(f"/books/{ISBN}/cover", headers=sysadmin_headers)
    assert response.status_code == 200
    assert response.json()["cover_url"] is None
    assert s3 == [key]


def test_deleting_a_book_deletes_its_cover(client, book, s3, sysadmin_headers):
    key = f"covers/{ISBN}/abc.png"
    client.put(f"/books/{ISBN}/cover", json={"key": key}, headers=sysadmin_headers)

    assert client.delete(f"/books/{ISBN}", headers=sysadmin_headers).status_code == 204
    assert s3 == [key]
