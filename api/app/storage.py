"""Portadas de libros sobre almacenamiento de objetos (S3 en AWS, MinIO en local).

Vive en la capa de `controllers` por la misma razón que `cache.py`: `services` y
`persistence` no saben que existe. Lo único que llega a la base es la **key** del
objeto (`covers/<isbn>/<uuid>.jpg`); la URL pública se arma acá al serializar, así
mudar de bucket, de región o meter CloudFront adelante no obliga a reescribir filas.

**El archivo nunca pasa por la API.** El browser pide una URL firmada
(`POST /books/{isbn}/cover-upload`), hace el `PUT` directo contra S3 y recién después
confirma la key (`PUT /books/{isbn}/cover`). En la arquitectura target eso evita que
subir 5 MB ocupe una tarea de ECS o el payload de API Gateway.

Sin `S3_BUCKET` la feature queda apagada: los endpoints de portada responden 503 y el
resto de la API funciona igual — así corren los tests.
"""

from __future__ import annotations

import logging
import uuid
from functools import lru_cache

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from .config import settings

logger = logging.getLogger(__name__)

# Formatos aceptados para una portada, y la extensión con la que se guarda cada uno.
# El content-type se firma dentro de la URL: S3 rechaza el PUT si el browser manda otro.
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class StorageDisabledError(RuntimeError):
    """No hay bucket configurado: la feature de portadas está apagada."""


def is_enabled() -> bool:
    return bool(settings.s3_bucket)


def _credentials() -> dict[str, str]:
    """Credenciales explícitas si están en el entorno; si no, la cadena default de boto3.

    En AWS lo correcto es no configurar ninguna y dejar que las tome del rol de la tarea
    (ECS) o de la función (Lambda). En local salen del `.env`, apuntando a MinIO.
    """
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        return {
            "aws_access_key_id": settings.aws_access_key_id,
            "aws_secret_access_key": settings.aws_secret_access_key,
        }
    return {}


@lru_cache(maxsize=None)
def _client(endpoint_url: str):
    """Cliente S3 para un endpoint dado. Cacheado: construirlo es caro."""
    return boto3.client(
        "s3",
        region_name=settings.s3_region,
        endpoint_url=endpoint_url or None,
        # SigV4 es lo que entienden tanto S3 como MinIO para URLs firmadas.
        config=Config(signature_version="s3v4"),
        **_credentials(),
    )


def _internal_client():
    """Para las operaciones del servidor (head/delete): endpoint de red interna."""
    return _client(settings.s3_endpoint_url)


def _signing_client():
    """Para firmar URLs que va a usar el **browser**.

    No es el mismo endpoint: SigV4 firma el `Host`, así que una URL firmada contra
    `http://storage:9000` (el nombre del servicio en compose) no sirve fuera de la red
    de Docker. En AWS las dos variables quedan vacías y ambos clientes apuntan a S3.
    """
    return _client(settings.s3_public_endpoint_url or settings.s3_endpoint_url)


def build_key(isbn: str, content_type: str) -> str:
    """Key nueva para una portada.

    Lleva un uuid y no solo el ISBN a propósito: al reemplazar una portada la URL cambia,
    así que ni el browser ni CloudFront sirven la imagen vieja desde su cache.
    """
    extension = ALLOWED_CONTENT_TYPES[content_type]
    return f"{settings.s3_cover_prefix}/{isbn}/{uuid.uuid4().hex}.{extension}"


def owns_key(isbn: str, key: str) -> bool:
    """¿Esa key pertenece a este libro? Evita apuntar la portada a un objeto ajeno."""
    return key.startswith(f"{settings.s3_cover_prefix}/{isbn}/")


def public_url(key: str | None) -> str | None:
    """URL de lectura de una portada.

    Con `S3_PUBLIC_BASE_URL` sale por ahí (CloudFront delante del bucket, que es como se
    sirve en la arquitectura target). Si no, se arma contra el endpoint público o, en su
    defecto, contra el dominio de S3 de la región.
    """
    if not key or not is_enabled():
        return None
    if settings.s3_public_base_url:
        return f"{settings.s3_public_base_url.rstrip('/')}/{key}"
    endpoint = settings.s3_public_endpoint_url or settings.s3_endpoint_url
    if endpoint:
        return f"{endpoint.rstrip('/')}/{settings.s3_bucket}/{key}"
    return f"https://{settings.s3_bucket}.s3.{settings.s3_region}.amazonaws.com/{key}"


def presign_upload(key: str, content_type: str) -> str:
    """URL firmada para que el browser haga `PUT` del archivo directo a S3."""
    if not is_enabled():
        raise StorageDisabledError("S3_BUCKET no está configurado")
    return _signing_client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=settings.s3_presign_expire_seconds,
    )


def exists(key: str) -> bool:
    """¿El objeto está realmente subido?

    Se chequea antes de guardar la key en la base: si el `PUT` del browser falló, la fila
    quedaría apuntando a una portada que no existe y el catálogo mostraría imágenes rotas.
    """
    if not is_enabled():
        return False
    try:
        _internal_client().head_object(Bucket=settings.s3_bucket, Key=key)
        return True
    except ClientError:
        return False
    except BotoCoreError as exc:
        logger.warning("no se pudo verificar la portada %s: %s", key, exc)
        return False


def delete(key: str | None) -> None:
    """Borra un objeto. Best-effort: un huérfano en el bucket no puede voltear la request.

    La fuente de verdad es la fila: si el borrado falla, el libro ya no apunta a esa key
    y el objeto queda para que lo limpie una lifecycle rule del bucket.
    """
    if not key or not is_enabled():
        return
    try:
        _internal_client().delete_object(Bucket=settings.s3_bucket, Key=key)
    except (BotoCoreError, ClientError) as exc:
        logger.warning("no se pudo borrar la portada %s: %s", key, exc)


def health() -> str:
    """Estado del storage para `/health`: `disabled`, `ok` o `down`."""
    if not is_enabled():
        return "disabled"
    try:
        _internal_client().head_bucket(Bucket=settings.s3_bucket)
        return "ok"
    except (BotoCoreError, ClientError):
        return "down"
