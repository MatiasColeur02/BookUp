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


def test_a_lost_conditional_write_that_reaches_the_edge_is_a_409(client):
    """Red de seguridad de `main.py`: `ConditionFailedError` (persistencia) sale como 409."""
    from app.main import app
    from app.persistence.errors import AlreadyExistsError, ConditionFailedError

    @app.get("/__boom/{kind}")
    def boom(kind: str):
        raise (AlreadyExistsError if kind == "exists" else ConditionFailedError)("lost the race")

    for kind in ("exists", "condition"):
        response = client.get(f"/__boom/{kind}")
        assert response.status_code == 409
        assert response.json() == {"detail": "lost the race"}
