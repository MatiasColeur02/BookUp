"""`app/identity.py` contra el `Stubber` de botocore: lo que se le pide a Cognito y cómo se
traducen sus errores. Es lo que `tests/fake_identity.py` da por hecho."""

import boto3
import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber

from app import identity
from app.config import settings

POOL = "us-east-1_TestPool"
SUB = "0f3c2a9e-1111-4222-8333-444455556666"
EMAIL = "biblio@example.com"


@pytest.fixture()
def stub(monkeypatch):
    monkeypatch.setattr(settings, "cognito_user_pool_id", POOL)
    client = boto3.client(
        "cognito-idp", region_name="us-east-1", aws_access_key_id="x", aws_secret_access_key="x"
    )
    monkeypatch.setattr(identity, "client", lambda: client)
    with Stubber(client) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


def user_response(attributes_key="Attributes"):
    return {
        "Username": SUB,
        attributes_key: [{"Name": "sub", "Value": SUB}, {"Name": "email", "Value": EMAIL}],
    }


ATTRIBUTES = [
    {"Name": "email", "Value": EMAIL},
    {"Name": "email_verified", "Value": "true"},
    {"Name": "name", "Value": "Biblio"},
]


def test_create_user_is_suppressed_verified_and_temporary(stub):
    stub.add_response(
        "admin_create_user",
        {"User": user_response()},
        {
            "UserPoolId": POOL,
            "Username": EMAIL,
            "UserAttributes": ATTRIBUTES,
            "TemporaryPassword": "temporal123",
            "MessageAction": "SUPPRESS",
        },
    )
    assert identity.create_user(email=EMAIL, name="Biblio", temporary_password="temporal123") == SUB


def test_create_user_translates_username_exists(stub):
    stub.add_client_error("admin_create_user", "UsernameExistsException")
    with pytest.raises(identity.UsernameExistsError):
        identity.create_user(email=EMAIL, name="Biblio", temporary_password="temporal123")


def test_create_user_translates_invalid_password(stub):
    stub.add_client_error(
        "admin_create_user", "InvalidPasswordException", "Password not long enough"
    )
    with pytest.raises(identity.InvalidPasswordError, match="Password not long enough"):
        identity.create_user(email=EMAIL, name="Biblio", temporary_password="temporal123")


def test_any_other_cognito_error_is_unavailable(stub):
    stub.add_client_error("admin_create_user", "TooManyRequestsException")
    with pytest.raises(identity.IdentityUnavailableError):
        identity.create_user(email=EMAIL, name="Biblio", temporary_password="temporal123")


def test_unreachable_cognito_is_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "cognito_user_pool_id", POOL)

    class Down:
        def admin_delete_user(self, **kwargs):
            raise EndpointConnectionError(endpoint_url="https://cognito-idp.us-east-1.amazonaws.com")

    monkeypatch.setattr(identity, "client", lambda: Down())
    with pytest.raises(identity.IdentityUnavailableError):
        identity.delete_user(SUB)


def test_without_a_pool_nothing_is_called(monkeypatch):
    monkeypatch.setattr(settings, "cognito_user_pool_id", "")
    with pytest.raises(identity.IdentityUnavailableError, match="COGNITO_USER_POOL_ID"):
        identity.delete_user(SUB)


def test_ensure_user_creates_and_sets_a_permanent_password(stub):
    stub.add_response(
        "admin_create_user",
        {"User": user_response()},
        {"UserPoolId": POOL, "Username": EMAIL, "UserAttributes": ATTRIBUTES, "MessageAction": "SUPPRESS"},
    )
    stub.add_response(
        "admin_set_user_password",
        {},
        {"UserPoolId": POOL, "Username": EMAIL, "Password": "bookup123", "Permanent": True},
    )
    assert identity.ensure_user(email=EMAIL, name="Biblio", password="bookup123") == SUB


def test_ensure_user_reuses_an_existing_account(stub):
    stub.add_client_error("admin_create_user", "UsernameExistsException")
    stub.add_response(
        "admin_get_user", user_response("UserAttributes"), {"UserPoolId": POOL, "Username": EMAIL}
    )
    stub.add_response(
        "admin_set_user_password",
        {},
        {"UserPoolId": POOL, "Username": EMAIL, "Password": "bookup123", "Permanent": True},
    )
    assert identity.ensure_user(email=EMAIL, name="Biblio", password="bookup123") == SUB


def test_delete_user(stub):
    stub.add_response("admin_delete_user", {}, {"UserPoolId": POOL, "Username": SUB})
    identity.delete_user(SUB)


def test_delete_of_a_missing_account_counts_as_done(stub):
    stub.add_client_error("admin_delete_user", "UserNotFoundException")
    identity.delete_user(SUB)  # no lanza
