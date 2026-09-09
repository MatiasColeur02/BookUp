"""Rate limiting de los endpoints públicos, sobre el mismo Redis que el cache.

Vive en la capa de `controllers` por la misma razón que `cache.py` y `storage.py`:
`services` y `persistence` no saben que existe. Lo que se cuenta son requests, que es un
concepto de HTTP, no del dominio.

**Qué protege.** `POST /auth/login` es el único endpoint que compara una contraseña, así
que sin freno se le puede tirar un diccionario entero: 1000 intentos por segundo contra
un email conocido. `POST /users` es el único alta pública, así que sin freno se puede
llenar la tabla de usuarios. Los dos son públicos y sin sesión.

**Ventana fija, no deslizante.** Un `INCR` con `EXPIRE` es una operación atómica y O(1),
y el peor caso de una ventana fija (2x el límite en el borde entre dos ventanas) es
irrelevante para lo que se está frenando. Una ventana deslizante necesita un sorted set
por clave, que cuesta memoria y CPU en un ElastiCache compartido.

**Fail-open, igual que el cache.** Si Redis no contesta, se deja pasar el request: un
nodo caído no puede voltear el login de todo el mundo. Es una decisión explícita —
prioriza disponibilidad sobre el freno, que es lo correcto para un límite anti-abuso y
no para un control de autorización (ese está en `dependencies.py` y no depende de Redis).
Sin `REDIS_URL` el límite queda apagado; así corre la suite.
"""

from __future__ import annotations

import logging

import redis
from fastapi import HTTPException, Request

from . import cache
from .config import settings

logger = logging.getLogger(__name__)

_PREFIX = "bookup:rl"


def client_ip(request: Request) -> str:
    """IP del cliente, mirando `X-Forwarded-For` si viene.

    Detrás de un ALB o de API Gateway la IP del socket es la del balanceador, así que
    contar por ella juntaría a todos los usuarios en una sola clave. El header lo puede
    falsificar cualquiera que llegue directo a la API, así que esto **solo** es confiable
    si el balanceador reescribe el header y la API no es alcanzable sin pasar por él —
    que es como queda en la VPC de la arquitectura target.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def hit(scope: str, identity: str, *, limit: int, window_seconds: int) -> None:
    """Cuenta un intento y lanza 429 si `identity` ya pasó `limit` en la ventana.

    `scope` separa los contadores de cada endpoint para que gastar los intentos de login
    no consuma los del registro.
    """
    if limit <= 0:
        return
    client = cache.get_client()
    if client is None:
        return

    key = f"{_PREFIX}:{scope}:{cache.digest(identity)}"
    try:
        pipe = client.pipeline()
        pipe.incr(key)
        # El EXPIRE va en cada hit y no solo en el primero: si se pisa un TTL por una
        # carrera entre dos requests, la ventana se corre pero nunca queda sin vencer.
        pipe.expire(key, window_seconds)
        count = pipe.execute()[0]
    except redis.RedisError as exc:
        # Mismo criterio que el cache: se deja pasar y se sigue sirviendo.
        logger.warning("rate limit no disponible (%s): se deja pasar el request", exc)
        return

    if count > limit:
        logger.warning("rate limit alcanzado en %s", scope)
        raise HTTPException(
            status_code=429,
            detail="Demasiados intentos. Esperá un momento y volvé a probar.",
            headers={"Retry-After": str(window_seconds)},
        )


def login_attempt(request: Request) -> None:
    """Freno por IP, **antes** de autenticar.

    Va antes a propósito: comparar un hash de bcrypt es caro por diseño, así que cortar
    acá es lo que impide que un solo origen queme CPU del servidor a fuerza de intentos.
    """
    hit(
        "login:ip",
        client_ip(request),
        limit=settings.rate_limit_login_per_ip,
        window_seconds=settings.rate_limit_window_seconds,
    )


def failed_login(email: str) -> None:
    """Freno por cuenta, **después** de que el intento falló.

    El contador por IP no ve el ataque distribuido: mil IPs probando diez contraseñas
    cada una contra la misma cuenta pasan enteras. Este lo corta.

    Que se cuente *después* de fallar, y no antes de autenticar, es la parte importante:
    si el chequeo fuera previo, cualquiera podría dejar a otra persona afuera de su
    propia cuenta tirándole diez contraseñas incorrectas. Contando solo los fallos, la
    contraseña correcta **siempre** entra y lo único que se bloquea es seguir adivinando.
    """
    hit(
        "login:email",
        email.strip().lower(),
        limit=settings.rate_limit_login_per_email,
        window_seconds=settings.rate_limit_window_seconds,
    )


def signup_attempt(request: Request) -> None:
    """Freno del auto-registro: por IP, para que no se llene la tabla de usuarios."""
    hit(
        "signup:ip",
        client_ip(request),
        limit=settings.rate_limit_signup_per_ip,
        window_seconds=settings.rate_limit_window_seconds,
    )
