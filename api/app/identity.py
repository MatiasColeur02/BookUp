"""Cuentas del User Pool de Cognito (`AUTH_MODE=cognito`, `COGNITO_ROADMAP.md` §5).

Hermano de `storage.py` y con el mismo criterio de capas: `services` y `persistence` no ven
boto3 ni Cognito. Los controllers orquestan (alta de personal con compensación, baja en
orden Cognito → DynamoDB) y el service recibe el `cognito_sub` como un valor más.

Las cuentas se crean con `MessageAction=SUPPRESS` y `email_verified=true`: el remitente
default de Cognito tiene una cuota diaria mínima (AWS Academy no permite SES) y los emails
del seed no existen. Por eso la contraseña la pone quien da el alta.

**Credenciales: siempre la cadena default de boto3**, nunca `AWS_ACCESS_KEY_ID` de los
settings como hace `storage.py` con MinIO: en AWS salen del rol de la tarea, y desde una
laptop las del lab son temporales y traen `AWS_SESSION_TOKEN`, que pasar solo la key y el
secreto perdería.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .config import settings

logger = logging.getLogger(__name__)


class IdentityError(Exception):
    """Base de los errores de este módulo."""


class IdentityUnavailableError(IdentityError):
    """Cognito no contesta o rechazó el pedido por algo que no es del usuario: un 503."""


class UsernameExistsError(IdentityError):
    """Ya hay una cuenta con ese email en el User Pool."""


class InvalidPasswordError(IdentityError):
    """La contraseña no cumple la política del User Pool."""


@lru_cache(maxsize=None)
def _client(region: str):
    return boto3.client("cognito-idp", region_name=region)


def client():
    return _client(settings.cognito_region)


def _pool_id() -> str:
    if not settings.cognito_user_pool_id:
        raise IdentityUnavailableError("COGNITO_USER_POOL_ID is not configured")
    return settings.cognito_user_pool_id


def _call(operation: str, **kwargs: Any) -> dict[str, Any]:
    """Una llamada a la API de administración, con sus errores traducidos."""
    try:
        return getattr(client(), operation)(UserPoolId=_pool_id(), **kwargs)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "UsernameExistsException":
            raise UsernameExistsError("A Cognito account with that email already exists") from exc
        if code == "InvalidPasswordException":
            # El mensaje de Cognito dice qué regla no cumple, y no trae datos sensibles.
            message = exc.response.get("Error", {}).get("Message", "Invalid password")
            raise InvalidPasswordError(message) from exc
        if code == "UserNotFoundException":
            raise
        logger.error("cognito-idp %s failed: %s", operation, code or exc)
        raise IdentityUnavailableError("The identity provider rejected the request") from exc
    except BotoCoreError as exc:
        logger.error("cognito-idp %s failed: %s", operation, type(exc).__name__)
        raise IdentityUnavailableError("Could not reach the identity provider") from exc


def _sub_of(attributes: list[dict[str, str]]) -> str:
    for attribute in attributes:
        if attribute["Name"] == "sub":
            return attribute["Value"]
    raise IdentityUnavailableError("Cognito returned a user without sub")


def _attributes(email: str, name: str) -> list[dict[str, str]]:
    return [
        {"Name": "email", "Value": email},
        {"Name": "email_verified", "Value": "true"},
        {"Name": "name", "Value": name},
    ]


def create_user(*, email: str, name: str, temporary_password: str) -> str:
    """Alta de personal: cuenta en `FORCE_CHANGE_PASSWORD`, que la Hosted UI obliga a cambiar
    en el primer ingreso. Devuelve el `sub`.

    La contraseña temporal va en el mismo `AdminCreateUser` (`TemporaryPassword`) y no en un
    `AdminSetUserPassword` aparte: una sola llamada, sin una cuenta a medio armar si la
    segunda falla.
    """
    response = _call(
        "admin_create_user",
        Username=email,
        UserAttributes=_attributes(email, name),
        TemporaryPassword=temporary_password,
        MessageAction="SUPPRESS",
    )
    return _sub_of(response["User"]["Attributes"])


def ensure_user(*, email: str, name: str, password: str) -> str:
    """Para el seed: la cuenta existe con esa contraseña **permanente** (entra directo, sin
    cambio obligatorio). Idempotente: si ya existe, la reusa. Devuelve el `sub`."""
    try:
        response = _call(
            "admin_create_user",
            Username=email,
            UserAttributes=_attributes(email, name),
            MessageAction="SUPPRESS",
        )
        sub = _sub_of(response["User"]["Attributes"])
    except UsernameExistsError:
        sub = _sub_of(_call("admin_get_user", Username=email)["UserAttributes"])
    _call("admin_set_user_password", Username=email, Password=password, Permanent=True)
    return sub


def delete_user(username: str) -> None:
    """Baja de la cuenta. Idempotente: una cuenta que ya no existe cuenta como borrada, así
    reintentar un `DELETE /users/{id}` que falló a mitad termina el trabajo.

    `username` puede ser el `sub` o el email: con `username_attributes = ["email"]` Cognito
    acepta los dos en las operaciones de administración.
    """
    try:
        _call("admin_delete_user", Username=username)
    except ClientError:  # solo llega acá `UserNotFoundException`
        logger.info("cognito-idp admin_delete_user: user already gone")
