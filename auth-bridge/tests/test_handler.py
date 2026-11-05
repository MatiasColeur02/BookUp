"""El puente sin AWS: el token endpoint de Cognito es un `urlopen` falso."""

import base64
import io
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

import pytest

import handler

FRONTEND = "http://bookup-front.s3-website-us-east-1.amazonaws.com"
CALLBACK = "https://abc123.execute-api.us-east-1.amazonaws.com/callback"
DOMAIN = "bookup-test.auth.us-east-1.amazoncognito.com"
CLIENT_ID = "test-client"
SECRET = "s3cr3t-client-secret-value"

CODE = "8f1c4d2e-0000-4111-8222-333344445555"
ACCESS = "eyJraWQiOiJhY2Nlc3MiLCJhbGciOiJSUzI1NiJ9.access-token-payload.signature"
ID_TOKEN = "eyJraWQiOiJpZCIsImFsZyI6IlJTMjU2In0.id-token-payload.signature"
REFRESH = "eyJjdHkiOiJKV1QiLCJlbmMiOiJBMjU2R0NNIn0.refresh-token.opaque"
STATE = "3b241101-e2bb-4255-8caf-4136c566a962"


class FakeTokenEndpoint:
    """`POST /oauth2/token`: guarda lo que le pidieron y contesta lo configurado."""

    def __init__(self):
        self.requests = []
        self.status = 200
        self.payload = {
            "access_token": ACCESS,
            "id_token": ID_TOKEN,
            "refresh_token": REFRESH,
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        self.unreachable = False

    def urlopen(self, request, timeout=None):
        self.requests.append(request)
        if self.unreachable:
            raise urllib.error.URLError("connection refused")
        body = json.dumps(self.payload).encode() if not isinstance(self.payload, bytes) else self.payload
        if self.status != 200:
            raise urllib.error.HTTPError(request.full_url, self.status, "error", {}, io.BytesIO(body))
        return io.BytesIO(body)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("COGNITO_DOMAIN", DOMAIN)
    monkeypatch.setenv("COGNITO_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("COGNITO_CLIENT_SECRET", SECRET)
    monkeypatch.setenv("CALLBACK_URL", CALLBACK)
    monkeypatch.setenv("FRONTEND_URL", FRONTEND)


@pytest.fixture(autouse=True)
def cognito(monkeypatch):
    fake = FakeTokenEndpoint()
    monkeypatch.setattr(urllib.request, "urlopen", fake.urlopen)
    return fake


def invoke(path="/callback", query="", method="GET"):
    """Un evento de API Gateway HTTP API, payload 2.0 (solo lo que el handler mira)."""
    event = {
        "version": "2.0",
        "rawPath": path,
        "rawQueryString": query,
        "requestContext": {"http": {"method": method, "path": path}},
    }
    return handler.lambda_handler(event, None)


def callback(**params):
    return invoke("/callback", urllib.parse.urlencode(params))


def fragment(response) -> dict[str, str]:
    """El destino tiene que ser la raíz del frontend; devuelve el fragmento parseado."""
    assert response["statusCode"] == 302
    location = response["headers"]["Location"]
    base, _, frag = location.partition("#")
    assert base == f"{FRONTEND}/"
    return dict(urllib.parse.parse_qsl(frag, keep_blank_values=True))


# ---------------------------------------------------------------------------
# Callback feliz
# ---------------------------------------------------------------------------


def test_code_is_exchanged_and_only_the_access_token_reaches_the_fragment(cognito):
    response = callback(code=CODE, state=STATE)

    assert fragment(response) == {"access_token": ACCESS, "expires_in": "3600", "state": STATE}
    location = response["headers"]["Location"]
    assert ID_TOKEN not in location and REFRESH not in location


def test_exchange_request_is_the_one_cognito_expects(cognito):
    callback(code=CODE, state=STATE)

    (request,) = cognito.requests
    assert request.get_method() == "POST"
    assert request.full_url == f"https://{DOMAIN}/oauth2/token"
    assert request.get_header("Content-type") == "application/x-www-form-urlencoded"
    expected = base64.b64encode(f"{CLIENT_ID}:{SECRET}".encode()).decode()
    assert request.get_header("Authorization") == f"Basic {expected}"
    assert dict(urllib.parse.parse_qsl(request.data.decode())) == {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": CODE,
        # Byte a byte la registrada en el app client.
        "redirect_uri": CALLBACK,
    }


def test_cognito_domain_may_come_with_scheme_and_trailing_slash(monkeypatch, cognito):
    monkeypatch.setenv("COGNITO_DOMAIN", f"https://{DOMAIN}/")
    callback(code=CODE, state=STATE)
    assert cognito.requests[0].full_url == f"https://{DOMAIN}/oauth2/token"


def test_redirect_headers_forbid_caching_and_referrer():
    headers = callback(code=CODE, state=STATE)["headers"]
    assert headers["Cache-Control"] == "no-store"
    assert headers["Referrer-Policy"] == "no-referrer"


def test_state_is_returned_url_encoded():
    state = "a b&c=d#e/ñ"
    response = callback(code=CODE, state=state)

    location = response["headers"]["Location"]
    # Ni `&`, ni `=`, ni `#` sin codificar: no pueden romper el fragmento.
    assert location.count("#") == 1
    assert fragment(response)["state"] == state


def test_repeated_parameters_keep_the_first_and_do_not_join_with_commas(cognito):
    response = invoke("/callback", f"code={CODE}&code=other&state=a,b&state=c")
    assert fragment(response)["state"] == "a,b"
    assert dict(urllib.parse.parse_qsl(cognito.requests[0].data.decode()))["code"] == CODE


# ---------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------


def test_error_from_cognito_redirects_without_exchanging(cognito):
    response = callback(error="access_denied", error_description="User cancelled", state=STATE)

    assert fragment(response) == {"error": "access_denied", "state": STATE}
    assert cognito.requests == []


def test_error_value_is_not_reflected_unless_it_looks_like_an_oauth_error(cognito):
    response = callback(error="<img src=x onerror=alert(1)>", state=STATE)
    assert fragment(response)["error"] == "unknown_error"


@pytest.mark.parametrize(
    "setup",
    [
        pytest.param(lambda c: setattr(c, "status", 400) or setattr(c, "payload", {"error": "invalid_grant"}), id="code reused or expired"),
        pytest.param(lambda c: setattr(c, "status", 500) or setattr(c, "payload", b"<html>oops</html>"), id="cognito 500"),
        pytest.param(lambda c: setattr(c, "unreachable", True), id="unreachable"),
        pytest.param(lambda c: setattr(c, "payload", b"not json"), id="invalid json"),
        pytest.param(lambda c: setattr(c, "payload", {"id_token": ID_TOKEN}), id="no access token"),
        pytest.param(lambda c: setattr(c, "payload", {"access_token": ACCESS, "expires_in": "3600"}), id="bad expires_in"),
    ],
)
def test_failed_exchange_redirects_with_exchange_failed(cognito, setup):
    setup(cognito)

    response = callback(code=CODE, state=STATE)

    assert fragment(response) == {"error": "exchange_failed", "state": STATE}
    assert response["body"] == ""


def test_missing_code_is_an_invalid_request(cognito):
    assert fragment(callback(state=STATE)) == {"error": "invalid_request", "state": STATE}
    assert cognito.requests == []


def test_oversized_code_is_not_sent_to_cognito(cognito):
    response = callback(code="x" * (handler.MAX_CODE_LENGTH + 1), state=STATE)
    assert fragment(response)["error"] == "invalid_request"
    assert cognito.requests == []


def test_too_long_state_is_rejected_without_exchanging_or_echoing_it(cognito):
    response = callback(code=CODE, state="s" * (handler.MAX_STATE_LENGTH + 1))

    assert fragment(response) == {"error": "invalid_request"}
    assert cognito.requests == []


def test_state_at_the_limit_is_accepted():
    state = "s" * handler.MAX_STATE_LENGTH
    assert fragment(callback(code=CODE, state=state))["state"] == state


# ---------------------------------------------------------------------------
# El destino no se puede cambiar desde el request
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra",
    [
        {"redirect_uri": "https://evil.example/steal"},
        {"returnTo": "https://evil.example"},
        {"next": "//evil.example"},
        {"frontend_url": "https://evil.example"},
        {"state": "https://evil.example/#"},
    ],
)
def test_no_parameter_changes_the_redirect_target(cognito, extra):
    params = {"code": CODE, "state": STATE, **extra}
    response = invoke("/callback", urllib.parse.urlencode(params))

    assert response["headers"]["Location"].startswith(f"{FRONTEND}/#")
    fragment(response)
    # Y el canje usa la callback configurada, no la del request.
    sent = dict(urllib.parse.parse_qsl(cognito.requests[0].data.decode()))
    assert sent["redirect_uri"] == CALLBACK


def test_frontend_url_trailing_slash_is_normalized(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", f"{FRONTEND}/")
    assert fragment(callback(code=CODE, state=STATE))["state"] == STATE


# ---------------------------------------------------------------------------
# Otras rutas
# ---------------------------------------------------------------------------


def test_signed_out_redirects_to_the_frontend_root(cognito):
    response = invoke("/signed-out", "redirect=https://evil.example")

    assert response["statusCode"] == 302
    assert response["headers"]["Location"] == f"{FRONTEND}/"
    assert response["headers"]["Cache-Control"] == "no-store"
    assert cognito.requests == []


def test_unknown_route_is_a_404():
    assert invoke("/oauth2/authorize")["statusCode"] == 404


def test_other_methods_are_not_allowed():
    assert invoke("/callback", f"code={CODE}", method="POST")["statusCode"] == 405


def test_missing_configuration_fails_loudly(monkeypatch):
    monkeypatch.delenv("COGNITO_CLIENT_SECRET")
    with pytest.raises(RuntimeError, match="COGNITO_CLIENT_SECRET"):
        callback(code=CODE, state=STATE)


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


SECRETS = (CODE, ACCESS, ID_TOKEN, REFRESH, SECRET, base64.b64encode(f"{CLIENT_ID}:{SECRET}".encode()).decode())


@pytest.mark.parametrize(
    "setup",
    [
        pytest.param(lambda c: None, id="success"),
        pytest.param(lambda c: setattr(c, "status", 400) or setattr(c, "payload", {"error": "invalid_grant", "error_description": CODE}), id="cognito rejects"),
        pytest.param(lambda c: setattr(c, "payload", {"refresh_token": REFRESH}), id="partial response"),
    ],
)
def test_no_code_token_or_secret_reaches_the_logs(cognito, caplog, capsys, setup):
    setup(cognito)
    caplog.set_level(logging.DEBUG)

    callback(code=CODE, state=STATE)

    out = capsys.readouterr()
    logged = caplog.text + out.out + out.err
    assert logged, "the handler should log something"
    for value in SECRETS:
        assert value not in logged


def test_rejected_exchange_logs_only_the_oauth_error_code(cognito, caplog):
    cognito.status = 400
    cognito.payload = {"error": "invalid_grant"}
    caplog.set_level(logging.INFO)

    callback(code=CODE, state=STATE)

    assert "HTTP 400 invalid_grant" in caplog.text
