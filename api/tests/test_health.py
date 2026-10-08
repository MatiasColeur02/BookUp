from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    # Sin REDIS_URL ni S3_BUCKET, cache y storage quedan apagados: así corre la suite. La
    # búsqueda corre contra el índice en proceso de los tests (ver `conftest.search_index`).
    body = response.json()
    assert body["status"] == "ok"
    assert set(body) == {"status", "cache", "storage", "search"}
    assert body["search"] == "ok"


def test_health_reports_search_disabled_without_a_url(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "opensearch_url", "")
    body = client.get("/health").json()
    assert body["search"] == "disabled"
    assert body["status"] == "ok"  # informativo: no baja el status general


def test_health_reports_search_down_when_it_does_not_answer(monkeypatch, search_index):
    monkeypatch.setattr(search_index, "ping", lambda: False)
    body = client.get("/health").json()
    assert body["search"] == "down"
    assert body["status"] == "ok"


def test_catalog_search_endpoints_answer_503_when_the_index_is_unavailable(client, monkeypatch):
    """Sin índice solo el catálogo con filtros y la búsqueda se caen; el resto sigue."""
    from app.persistence import search
    from app.persistence.errors import SearchUnavailableError

    def unavailable():
        raise SearchUnavailableError("The search index is not reachable")

    monkeypatch.setattr(search, "get_index", unavailable)

    for path in ("/books", "/books/search?q=algo", "/books/cities"):
        response = client.get(path)
        assert response.status_code == 503, path
        assert response.headers["retry-after"] == "5"
        assert "not reachable" in response.json()["detail"]
    assert client.get("/authors").status_code == 200  # lo demás sigue andando


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
