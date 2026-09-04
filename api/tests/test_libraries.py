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
