"""Cache de lecturas sobre Redis (ElastiCache for Redis en AWS).

Vive en la capa de `controllers` a propósito: lo que se guarda son payloads JSON ya
serializados por los esquemas Pydantic, no entidades ORM (que no son serializables y
lazy-loadean fuera de la sesión de SQLAlchemy). `services` y `persistence` siguen sin
enterarse de que el cache existe, igual que no se enteran de HTTP.

**Invalidación por generaciones.** Cada namespace tiene un contador (`bookup:ver:<ns>`)
cuyo valor se embebe en la clave. Invalidar es un `INCR` O(1) sobre ese contador: las
claves de la generación vieja quedan huérfanas y las limpia su propio TTL. Es la
alternativa a barrer claves con `KEYS`/`SCAN`, que en ElastiCache bloquea el nodo.
El costo es un round trip extra por lectura (primero el contador, después el dato);
contra una query a RDS, sale barato.

**El cache nunca puede tirar abajo la API.** Todo error de Redis se traga: se sirve
desde la base y se abre un breaker que apaga el cache unos segundos, para que un nodo
caído no le sume dos timeouts de socket a cada request.

Sin `REDIS_URL` el cache queda apagado y la API funciona exactamente igual, solo que
cada lectura va a la base. Ese es el modo en que corren los tests.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from functools import lru_cache
from typing import Any, Callable

import redis
from pydantic import TypeAdapter

from .config import settings

logger = logging.getLogger(__name__)

# Namespaces: la unidad de invalidación. Agrupan lo que cambia junto.
NS_CATALOG = "catalog"
NS_AVAILABILITY = "availability"
NS_LIBRARIES = "libraries"
NS_AUTHORS = "authors"
NS_GENRES = "genres"

# TTLs en segundos. Son el techo de desactualización si una invalidación se pierde
# (Redis reiniciado, o una escritura hecha por fuera de la API como `python -m app.seed`).
TTL_CATALOG = 300
TTL_SEARCH = 120
TTL_AVAILABILITY = 30  # cambia con cada reserva: TTL corto además de la invalidación
TTL_REFERENCE = 600  # sedes/autores/géneros: casi nunca cambian

_PREFIX = "bookup"

# Tras un error de Redis dejamos de intentarlo un rato. Sin esto, con ElastiCache caído
# cada request pagaría los timeouts de socket antes de ir igual a la base.
_BREAKER_COOLDOWN_SECONDS = 10.0

_client: redis.Redis | None = None
_breaker_until = 0.0


def get_client() -> redis.Redis | None:
    """El cliente Redis, o `None` si el cache está apagado (sin `REDIS_URL`)."""
    global _client
    if not settings.redis_url:
        return None
    if _client is None:
        _client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=settings.redis_timeout_seconds,
            socket_connect_timeout=settings.redis_timeout_seconds,
        )
    return _client


def _live_client() -> redis.Redis | None:
    """El cliente, salvo que el breaker esté abierto por un error reciente."""
    if time.monotonic() < _breaker_until:
        return None
    return get_client()


def _trip_breaker(exc: Exception) -> None:
    global _breaker_until
    _breaker_until = time.monotonic() + _BREAKER_COOLDOWN_SECONDS
    logger.warning(
        "cache no disponible, se sirve desde la base por %.0fs: %s",
        _BREAKER_COOLDOWN_SECONDS,
        exc,
    )


def _versioned_key(client: redis.Redis, namespace: str, key: str) -> str:
    """La clave de la generación vigente del namespace.

    El contador se escribe con INCR y a propósito no lleva TTL: si desapareciera, se
    volvería a leer como 0 y las entradas viejas de la generación 0 que todavía no
    vencieron volverían a ser visibles. Por eso el servidor tiene que correr con
    `maxmemory-policy volatile-lru`, que solo desaloja claves con TTL — es el default de
    ElastiCache, y está fijado explícitamente en `docker-compose.yml`.
    """
    version = client.get(f"{_PREFIX}:ver:{namespace}") or "0"
    return f"{_PREFIX}:{namespace}:v{version}:{key}"


@lru_cache(maxsize=None)
def _adapter(model: Any) -> TypeAdapter:
    """`TypeAdapter` es caro de construir y el modelo de cada endpoint es fijo."""
    return TypeAdapter(model)


def _serialize(model: Any, value: Any) -> Any:
    """Pasa lo que devuelve un service (entidades ORM) al payload JSON del endpoint.

    El `validate_python` no es opcional: `dump_python` sobre una entidad ORM la serializa
    como objeto arbitrario y se come las relaciones (un `BookOut` saldría sin autores ni
    géneros). Validar primero es lo que aplica el `from_attributes` de los esquemas.
    """
    adapter = _adapter(model)
    return adapter.dump_python(adapter.validate_python(value, from_attributes=True), mode="json")


def digest(value: str) -> str:
    """Hash corto para meter texto libre (una query de búsqueda) en una clave.

    Se hashea el texto crudo, sin normalizar: dos queries distintas nunca comparten
    entrada, aunque eso cueste algún hit de menos.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def cached(namespace: str, key: str, *, ttl: int, model: Any, loader: Callable[[], Any]) -> Any:
    """Devuelve el payload JSON de `loader()`, sirviéndolo de Redis si ya estaba.

    Lo que vuelve son datos JSON planos, no entidades: FastAPI los revalida contra el
    `response_model` del endpoint, así que un hit y un miss producen la misma respuesta.
    """
    client = _live_client()
    if client is None:
        return _serialize(model, loader())

    try:
        full_key = _versioned_key(client, namespace, key)
        hit = client.get(full_key)
        if hit is not None:
            return json.loads(hit)
    except (redis.RedisError, ValueError) as exc:
        _trip_breaker(exc)
        return _serialize(model, loader())

    payload = _serialize(model, loader())
    try:
        client.setex(full_key, ttl, json.dumps(payload))
    except redis.RedisError as exc:
        _trip_breaker(exc)
    return payload


def invalidate(*namespaces: str) -> None:
    """Marca obsoleto todo lo cacheado en esos namespaces: un `INCR` por namespace.

    Si falla, no se propaga: la escritura en la base ya está hecha y romper la respuesta
    del endpoint sería peor que servir datos viejos hasta que venza el TTL.
    """
    client = _live_client()
    if client is None:
        return
    try:
        pipe = client.pipeline()
        for namespace in namespaces:
            pipe.incr(f"{_PREFIX}:ver:{namespace}")
        pipe.execute()
    except redis.RedisError as exc:
        _trip_breaker(exc)


def health() -> str:
    """Estado del cache para `/health`: `disabled`, `ok` o `down`."""
    client = get_client()
    if client is None:
        return "disabled"
    try:
        client.ping()
        return "ok"
    except redis.RedisError:
        return "down"
