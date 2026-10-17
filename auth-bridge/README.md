# auth-bridge

Lambda que hace de **URL HTTPS** entre la Hosted UI de Cognito y el frontend, que en AWS
Academy vive en el website endpoint de S3 (HTTP) y por eso no se puede registrar como
callback. Diseño y motivos en [`COGNITO_ROADMAP.md`](../COGNITO_ROADMAP.md) §2 y §3.

Python 3.12, **solo biblioteca estándar**: el paquete de la Lambda es `handler.py` y nada más
(sin capa de dependencias). No comparte código con `api/`.

## Contrato

Handler: `handler.lambda_handler`, detrás de un **API Gateway HTTP API** con integración
`AWS_PROXY` y `payload_format_version = "2.0"`. Enruta por `rawPath`.

| Request | Respuesta |
|---|---|
| `GET /callback?code=&state=` | Canjea el code en `POST https://<COGNITO_DOMAIN>/oauth2/token` (HTTP Basic con el client secret, `redirect_uri = CALLBACK_URL`) y responde `302` a `<FRONTEND_URL>/#access_token=…&expires_in=…&state=…` |
| `GET /callback?error=&state=` | `302` a `<FRONTEND_URL>/#error=<error>&state=…`, sin canjear |
| `GET /callback` con el canje fallido (code vencido o reusado, Cognito caído, respuesta inválida) | `302` a `<FRONTEND_URL>/#error=exchange_failed&state=…` |
| `GET /callback` sin `code`, o con `code`/`state` demasiado largos | `302` a `<FRONTEND_URL>/#error=invalid_request` (el `state` no se devuelve si es el que se pasó del tope) |
| `GET /signed-out` | `302` a `<FRONTEND_URL>/` (destino del `/logout` de Cognito) |
| Otra ruta / otro método | `404` / `405` |

Todas las redirecciones llevan `Cache-Control: no-store` y `Referrer-Policy: no-referrer`.

Valores de `error` que puede ver el frontend: los de OAuth que manda Cognito
(`access_denied`, `invalid_request`, …), más `exchange_failed`, `invalid_request` y
`unknown_error` (un `error` de la query que no tiene forma de código OAuth: la query la puede
armar cualquiera, así que no se refleja tal cual).

### Reglas

- **El destino sale solo de `FRONTEND_URL`.** Ningún parámetro del request lo cambia; si no,
  el puente sería un open redirect que entrega tokens a cualquier dominio.
- **Al fragmento va solo** `access_token`, `expires_in` y `state`. El id token y el refresh
  token de la respuesta de Cognito se descartan.
- **El `state` no se valida acá** (lo genera y lo valida el frontend): se devuelve tal cual,
  URL-encodeado, con un tope de 128 caracteres.
- **Nunca se loguean** el code, los tokens ni el secreto. De un canje rechazado se loguea solo
  el status y el código OAuth (`HTTP 400 invalid_grant`).
- Los parámetros salen de `rawQueryString`: `queryStringParameters` une los repetidos con
  comas. Si un parámetro se repite, gana el primero.
- Si falta una variable de entorno, la invocación falla con un error que las nombra (un 500
  de API Gateway): es un error de despliegue, no de un usuario.

## Variables de entorno

Las completa la infraestructura (matriz de `COGNITO_ROADMAP.md` §8.3).

| Variable | Ejemplo | De dónde sale |
|---|---|---|
| `COGNITO_DOMAIN` | `bookup-grupo1.auth.us-east-1.amazoncognito.com` (con o sin `https://`) | `aws_cognito_user_pool_domain` |
| `COGNITO_CLIENT_ID` | `1h2j3k…` | `aws_cognito_user_pool_client.id` |
| `COGNITO_CLIENT_SECRET` | — | `aws_cognito_user_pool_client.client_secret` (**solo** acá) |
| `CALLBACK_URL` | `https://<api-id>.execute-api.us-east-1.amazonaws.com/callback` | La misma string registrada en el app client y usada en `/oauth2/authorize` |
| `FRONTEND_URL` | `http://<bucket>.s3-website-us-east-1.amazonaws.com` | Bucket S3 con website hosting |

## Tests

Sin AWS: el token endpoint de Cognito es un `urlopen` falso. Corren con cualquier Python 3.12
con `pytest`; lo más práctico es la imagen de la API:

```bash
docker compose run --rm --no-deps -v "$PWD/auth-bridge:/bridge" -w /bridge api pytest -p no:cacheprovider
```

(desde la raíz del repo). O, con un virtualenv propio: `cd auth-bridge && pytest`.
