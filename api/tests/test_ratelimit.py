"""Freno de fuerza bruta sobre el login y de alta masiva sobre el registro.

La suite corre con el cache apagado, así que estos tests encienden un Redis falso —el
mismo que usa el rate limiter— y cuentan los `INCR`. Lo que se verifica es la política
(cuántos intentos, contra qué clave, y qué pasa si Redis se cae), no la expiración: de
los TTL se ocupa el propio Redis.
"""

import pytest
import redis

from app import cache
from app.config import settings
from app.persistence.entities import UserRole


class FakeRedis:
    """Los comandos que usa `app.ratelimit`: `incr` y `expire`, vía pipeline."""

    def __init__(self):
        self.store: dict[str, int] = {}
        self.expires: dict[str, int] = {}
        self.fail = False

    def pipeline(self) -> "FakePipeline":
        return FakePipeline(self)


class FakePipeline:
    def __init__(self, client: FakeRedis):
        self.client = client
        self.ops: list[tuple] = []

    def incr(self, key: str) -> "FakePipeline":
        self.ops.append(("incr", key))
        return self

    def expire(self, key: str, ttl: int) -> "FakePipeline":
        self.ops.append(("expire", key, ttl))
        return self

    def execute(self) -> list:
        if self.client.fail:
            raise redis.ConnectionError("cache caído")
        results = []
        for op in self.ops:
            if op[0] == "incr":
                self.client.store[op[1]] = self.client.store.get(op[1], 0) + 1
                results.append(self.client.store[op[1]])
            else:
                self.client.expires[op[1]] = op[2]
                results.append(True)
        self.ops.clear()
        return results


@pytest.fixture()
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(settings, "redis_url", "redis://fake:6379/0")
    monkeypatch.setattr(cache, "_client", fake)
    monkeypatch.setattr(cache, "_breaker_until", 0.0)
    return fake


@pytest.fixture()
def customer(make_user):
    return make_user(UserRole.customer)


def _login(client, email: str, password: str = "no-es-la-password"):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_login_is_throttled_per_ip(client, customer, fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_login_per_ip", 3)
    monkeypatch.setattr(settings, "rate_limit_login_per_email", 1000)

    # Los primeros intentos fallan por credenciales, no por el freno.
    for _ in range(3):
        assert _login(client, customer.email).status_code == 401

    blocked = _login(client, customer.email)
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == str(settings.rate_limit_window_seconds)


def test_the_email_counter_catches_a_distributed_attack(client, customer, fake_redis, monkeypatch):
    """Cambiar de IP en cada intento esquiva el contador por IP, no el de la cuenta."""
    monkeypatch.setattr(settings, "rate_limit_login_per_ip", 1000)
    monkeypatch.setattr(settings, "rate_limit_login_per_email", 3)

    for n in range(3):
        response = _login(client, customer.email)
        assert response.status_code == 401, f"intento {n}"

    assert _login(client, customer.email).status_code == 429


def test_the_email_counter_is_case_insensitive(client, customer, fake_redis, monkeypatch):
    """Si no, alternar mayúsculas daría un contador nuevo por cada variante del email."""
    monkeypatch.setattr(settings, "rate_limit_login_per_ip", 1000)
    monkeypatch.setattr(settings, "rate_limit_login_per_email", 2)

    assert _login(client, customer.email).status_code == 401
    assert _login(client, customer.email.upper()).status_code == 401
    assert _login(client, customer.email.title()).status_code == 429


def test_the_account_limit_never_locks_the_real_owner_out(client, customer, fake_redis, monkeypatch):
    """Lo que se frena es seguir adivinando, no la cuenta: la contraseña correcta entra.

    Si el contador por email se chequeara *antes* de autenticar, cualquiera dejaría a
    otra persona afuera de su propia cuenta con diez intentos fallidos. Por eso solo se
    cuentan los fallos y el chequeo va después.
    """
    from tests.conftest import PASSWORD

    monkeypatch.setattr(settings, "rate_limit_login_per_ip", 1000)
    monkeypatch.setattr(settings, "rate_limit_login_per_email", 2)

    assert _login(client, customer.email).status_code == 401
    assert _login(client, customer.email).status_code == 401
    # Ya está pasado el límite: otro intento a ciegas se rechaza...
    assert _login(client, customer.email).status_code == 429
    # ...pero el dueño de la cuenta entra igual.
    ok = client.post("/auth/login", json={"email": customer.email, "password": PASSWORD})
    assert ok.status_code == 200


def test_a_throttled_account_does_not_affect_another_one(client, make_user, fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_login_per_ip", 1000)
    monkeypatch.setattr(settings, "rate_limit_login_per_email", 2)
    victim = make_user(UserRole.customer, email="victima@bookup.example")
    other = make_user(UserRole.customer, email="otro@bookup.example")

    assert _login(client, victim.email).status_code == 401
    assert _login(client, victim.email).status_code == 401
    assert _login(client, victim.email).status_code == 429
    # La otra cuenta sigue pudiendo intentar desde la misma IP.
    assert _login(client, other.email).status_code == 401


def test_a_correct_login_still_works_under_the_limit(client, customer, fake_redis, monkeypatch):
    from tests.conftest import PASSWORD

    monkeypatch.setattr(settings, "rate_limit_login_per_ip", 5)
    response = client.post("/auth/login", json={"email": customer.email, "password": PASSWORD})
    assert response.status_code == 200


def test_signup_is_throttled_per_ip(client, fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_signup_per_ip", 2)

    for n in range(2):
        response = client.post(
            "/users",
            json={"email": f"nuevo{n}@bookup.example", "password": "secret123", "name": "Nuevo"},
        )
        assert response.status_code == 201

    blocked = client.post(
        "/users",
        json={"email": "nuevo99@bookup.example", "password": "secret123", "name": "Nuevo"},
    )
    assert blocked.status_code == 429


def test_the_limit_is_off_without_redis(client, customer, monkeypatch):
    """Sin `REDIS_URL` la API funciona igual, solo que sin freno. Así corre la suite."""
    monkeypatch.setattr(settings, "rate_limit_login_per_ip", 1)

    for _ in range(5):
        assert _login(client, customer.email).status_code == 401


def test_a_redis_failure_does_not_break_the_login(client, customer, fake_redis, monkeypatch):
    """Fail-open: un nodo caído no puede dejar a todo el mundo afuera de la aplicación."""
    from tests.conftest import PASSWORD

    monkeypatch.setattr(settings, "rate_limit_login_per_ip", 1)
    fake_redis.fail = True

    response = client.post("/auth/login", json={"email": customer.email, "password": PASSWORD})
    assert response.status_code == 200
