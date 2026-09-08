from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    # Sin REDIS_URL el cache queda apagado, que es como corre la suite.
    assert response.json() == {"status": "ok", "cache": "disabled"}
