"""Triggers de Lambda del User Pool de Cognito (`COGNITO_ROADMAP.md` §5.1).

    handler: app.cognito_triggers.post_confirmation

Se empaqueta desde `api/` igual que la Lambda del indexador (`app/indexer.py`): reutiliza
`user_service` y los repositories. Lee `DYNAMO_TABLE` y `AWS_REGION` del entorno, como la API.

**Post Confirmation**: cuando un lector confirma su registro en la Hosted UI, crea su `User`
(`customer`) en DynamoDB, vinculado por el `sub`. Reglas:

- Solo con `PostConfirmation_ConfirmSignUp`. Cognito también lo invoca al confirmar un
  «olvidé mi contraseña» (`PostConfirmation_ConfirmForgotPassword`), y ahí el usuario ya existe.
- Idempotente por `sub`: Cognito reintenta el trigger si falla o tarda más de ~5 s.
- Valida `name` y `email` con los topes de `schemas.py`. Si no cumplen, lanza: la Hosted UI
  muestra el error y no queda un `User` con datos sin techo.
- Devuelve siempre el `event`: cualquier otra cosa, para Cognito, es un trigger fallido.
"""

from __future__ import annotations

import logging
from typing import Any

from .controllers.schemas import CognitoSignUp
from .persistence.dynamo import get_dynamo
from .services import user_service

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

CONFIRM_SIGN_UP = "PostConfirmation_ConfirmSignUp"


def post_confirmation(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    source = event.get("triggerSource")
    if source != CONFIRM_SIGN_UP:
        logger.info("post_confirmation: ignoring %s", source)
        return event

    attributes = event.get("request", {}).get("userAttributes", {})
    signup = CognitoSignUp(
        email=attributes.get("email"),
        name=attributes.get("name"),
        sub=attributes.get("sub"),
    )
    user = user_service.register_cognito_user(
        get_dynamo(), email=signup.email, name=signup.name, cognito_sub=signup.sub
    )
    # El id y no el email: los logs van a CloudWatch.
    logger.info("post_confirmation: user %s registered", user.id)
    return event
