"""Puente HTTPS entre la Hosted UI de Cognito y el frontend en S3 (`COGNITO_ROADMAP.md` §3).

Cognito solo redirige a URLs HTTPS, y el frontend vive en el website endpoint de S3, que es
HTTP. Esta Lambda, detrás de un API Gateway HTTP API (payload 2.0), es la URL HTTPS que
Cognito sí acepta:

- `GET /callback?code=&state=`: canjea el code por tokens con el client secret y redirige a
  `<FRONTEND_URL>/#access_token=…&expires_in=…&state=…`.
- `GET /callback?error=&state=`: el usuario canceló o Cognito rechazó; redirige con
  `#error=…&state=…` sin canjear nada.
- `GET /signed-out`: destino del `/logout` de Cognito; redirige a `<FRONTEND_URL>/`.

Solo biblioteca estándar: el zip es este archivo. Reglas que no se negocian:

- El destino del redirect sale **solo** de `FRONTEND_URL`, nunca del request: si no, el
  puente es un open redirect que le entrega tokens a cualquier dominio.
- El `redirect_uri` del canje es exactamente `CALLBACK_URL` (Cognito compara byte a byte).
- Al fragmento va solo `access_token`, `expires_in` y `state`: ni el id token ni el refresh.
- Nunca se loguean el code, los tokens ni el secreto: los logs van a CloudWatch.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("bookup.auth_bridge")
logger.setLevel(logging.INFO)

# El `state` lo genera el frontend (`crypto.randomUUID()`, 36 caracteres) y lo valida él;
# acá solo se acota, para que nadie meta un fragmento de kilobytes en la redirección.
MAX_STATE_LENGTH = 128
# El code de Cognito es un UUID; el tope es holgado y solo evita mandar basura al token endpoint.
MAX_CODE_LENGTH = 512
# Los `error` de OAuth son tokens cortos en snake_case (`access_denied`, `invalid_request`).
# Lo que llega en la query es de quien sea, así que cualquier otra cosa se reemplaza.
_OAUTH_ERROR = re.compile(r"^[a-z_]{1,64}$")
# El token endpoint de Cognito contesta en milisegundos; si no, mejor un error rápido que
# una Lambda colgada hasta su timeout.
EXCHANGE_TIMEOUT_SECONDS = 5

_REDIRECT_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
}


@dataclass(frozen=True)
class Config:
    cognito_domain: str
    client_id: str
    client_secret: str
    callback_url: str
    frontend_url: str

    @classmethod
    def from_env(cls) -> "Config":
        names = (
            "COGNITO_DOMAIN",
            "COGNITO_CLIENT_ID",
            "COGNITO_CLIENT_SECRET",
            "CALLBACK_URL",
            "FRONTEND_URL",
        )
        missing = [n for n in names if not os.environ.get(n)]
        if missing:
            raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")
        domain = os.environ["COGNITO_DOMAIN"]
        # Se acepta el dominio con o sin esquema: el output de Terraform es solo el host.
        if not domain.startswith("https://"):
            domain = f"https://{domain}"
        return cls(
            cognito_domain=domain.rstrip("/"),
            client_id=os.environ["COGNITO_CLIENT_ID"],
            client_secret=os.environ["COGNITO_CLIENT_SECRET"],
            callback_url=os.environ["CALLBACK_URL"],
            frontend_url=os.environ["FRONTEND_URL"].rstrip("/"),
        )


class ExchangeError(Exception):
    """El canje del code falló. El mensaje es apto para logs: nunca lleva code ni tokens."""


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    config = Config.from_env()
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "")

    if method != "GET":
        return {"statusCode": 405, "headers": {"Allow": "GET"}, "body": ""}
    if path == "/callback":
        return _callback(config, _query(event))
    if path == "/signed-out":
        logger.info("signed-out: redirecting to the frontend")
        return _redirect(f"{config.frontend_url}/")
    return {"statusCode": 404, "body": ""}


def _query(event: dict[str, Any]) -> dict[str, str]:
    """La query, del `rawQueryString`. `queryStringParameters` une los repetidos con comas,
    lo que cambiaría un `state` con coma; acá gana la primera aparición."""
    parsed = urllib.parse.parse_qs(event.get("rawQueryString", ""), keep_blank_values=True)
    return {name: values[0] for name, values in parsed.items()}


def _callback(config: Config, query: dict[str, str]) -> dict[str, Any]:
    state = query.get("state", "")
    if len(state) > MAX_STATE_LENGTH:
        logger.info("callback: state too long (%d chars), not exchanging", len(state))
        return _to_frontend(config, error="invalid_request")

    if "error" in query:
        error = query["error"] if _OAUTH_ERROR.match(query["error"]) else "unknown_error"
        logger.info("callback: Cognito returned error=%s", error)
        return _to_frontend(config, error=error, state=state)

    code = query.get("code", "")
    if not code or len(code) > MAX_CODE_LENGTH:
        logger.info("callback: missing or oversized code")
        return _to_frontend(config, error="invalid_request", state=state)

    try:
        access_token, expires_in = _exchange(config, code)
    except ExchangeError as exc:
        logger.warning("callback: code exchange failed: %s", exc)
        return _to_frontend(config, error="exchange_failed", state=state)

    logger.info("callback: code exchanged, redirecting with an access token")
    return _to_frontend(
        config, access_token=access_token, expires_in=str(expires_in), state=state
    )


def _exchange(config: Config, code: str) -> tuple[str, int]:
    """`POST /oauth2/token` con `grant_type=authorization_code`, autenticado con el secreto
    (HTTP Basic). Devuelve el access token y su duración; el resto de la respuesta se tira."""
    credentials = base64.b64encode(
        f"{config.client_id}:{config.client_secret}".encode()
    ).decode()
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": config.client_id,
            "code": code,
            "redirect_uri": config.callback_url,
        }
    ).encode()
    request = urllib.request.Request(
        f"{config.cognito_domain}/oauth2/token",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=EXCHANGE_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        # El cuerpo de error de Cognito es `{"error": "invalid_grant"}`: solo ese campo
        # se loguea, nunca el cuerpo entero.
        raise ExchangeError(f"HTTP {exc.code} {_oauth_error(exc)}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ExchangeError(f"token endpoint unreachable ({type(exc).__name__})") from None
    except ValueError:
        raise ExchangeError("token endpoint returned invalid JSON") from None

    access_token = payload.get("access_token") if isinstance(payload, dict) else None
    expires_in = payload.get("expires_in") if isinstance(payload, dict) else None
    if not isinstance(access_token, str) or not access_token:
        raise ExchangeError("token response without access_token")
    if not isinstance(expires_in, int) or isinstance(expires_in, bool) or expires_in <= 0:
        raise ExchangeError("token response without a valid expires_in")
    return access_token, expires_in


def _oauth_error(exc: urllib.error.HTTPError) -> str:
    try:
        error = json.load(exc).get("error", "")
    except Exception:
        return "(no error code)"
    return error if isinstance(error, str) and _OAUTH_ERROR.match(error) else "(no error code)"


def _to_frontend(config: Config, **fragment: str) -> dict[str, Any]:
    """Redirección a la raíz del frontend con los datos en el fragmento: el fragmento no
    sale del navegador (no llega a S3, ni a sus logs, ni al `Referer`). A la raíz porque el
    website endpoint de S3 solo sirve `index.html` sin error ahí."""
    values = {k: v for k, v in fragment.items() if v}
    return _redirect(f"{config.frontend_url}/#{urllib.parse.urlencode(values, quote_via=urllib.parse.quote)}")


def _redirect(location: str) -> dict[str, Any]:
    return {"statusCode": 302, "headers": {"Location": location, **_REDIRECT_HEADERS}, "body": ""}
