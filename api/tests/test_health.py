from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    # Sin REDIS_URL ni S3_BUCKET, cache y storage quedan apagados: así corre la suite.
    body = response.json()
    assert body["status"] == "ok"
    assert set(body) == {"status", "cache", "storage"}
