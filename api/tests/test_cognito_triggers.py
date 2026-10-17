"""El trigger Post Confirmation (`app/cognito_triggers.py`), con eventos como los de Cognito."""

import copy

import pytest
from pydantic import ValidationError

from app import cognito_triggers
from app.persistence.entities import User, UserRole
from app.persistence.repositories import UserRepository

SUB = "0f3c2a9e-1111-4222-8333-444455556666"


def event(source="PostConfirmation_ConfirmSignUp", **attributes):
    return {
        "version": "1",
        "triggerSource": source,
        "region": "us-east-1",
        "userPoolId": "us-east-1_TestPool",
        "userName": SUB,
        "callerContext": {"awsSdkVersion": "aws-sdk-unknown-unknown", "clientId": "test-app-client"},
        "request": {
            "userAttributes": {
                "sub": SUB,
                "email_verified": "true",
                "cognito:user_status": "CONFIRMED",
                "name": "Ana Lectora",
                "email": "Ana@Example.com",
                **attributes,
            }
        },
        "response": {},
    }


@pytest.fixture(autouse=True)
def dynamo(monkeypatch, db):
    monkeypatch.setattr(cognito_triggers, "get_dynamo", lambda: db)
    return db


def test_confirm_sign_up_creates_a_linked_customer(db):
    incoming = event()
    returned = cognito_triggers.post_confirmation(copy.deepcopy(incoming), None)

    assert returned == incoming  # Cognito necesita el evento de vuelta, intacto
    user = UserRepository(db).get_by_cognito_sub(SUB)
    assert user.role is UserRole.customer and user.library_id is None
    assert user.email == "ana@example.com"  # en minúsculas, como en todos los caminos
    assert user.name == "Ana Lectora"
    assert user.password_hash is None
    assert UserRepository(db).get_by_email("ana@example.com").id == user.id


def test_is_idempotent_when_cognito_retries(db):
    cognito_triggers.post_confirmation(event(), None)
    returned = cognito_triggers.post_confirmation(event(), None)

    assert returned == event()
    assert len(UserRepository(db).list_all()) == 1


def test_a_retry_does_not_overwrite_changes_made_since(db):
    cognito_triggers.post_confirmation(event(), None)
    user = UserRepository(db).get_by_cognito_sub(SUB)
    UserRepository(db).update(user.id, name="Cambiado")

    cognito_triggers.post_confirmation(event(), None)

    assert UserRepository(db).get(user.id).name == "Cambiado"


@pytest.mark.parametrize(
    "source",
    ["PostConfirmation_ConfirmForgotPassword", "PreSignUp_SignUp", None],
)
def test_other_trigger_sources_are_ignored(db, source):
    incoming = event(source)
    assert cognito_triggers.post_confirmation(copy.deepcopy(incoming), None) == incoming
    assert UserRepository(db).list_all() == []


def test_forgot_password_of_an_existing_user_does_not_duplicate_it(db):
    cognito_triggers.post_confirmation(event(), None)
    cognito_triggers.post_confirmation(event("PostConfirmation_ConfirmForgotPassword"), None)
    assert len(UserRepository(db).list_all()) == 1


@pytest.mark.parametrize(
    "attributes",
    [
        {"name": "x" * 151},
        {"name": "   "},
        {"name": None},
        {"email": "not-an-email"},
        {"email": f"{'a' * 250}@example.com"},
        {"sub": "s" * 129},
    ],
)
def test_attributes_beyond_the_schema_limits_fail_the_confirmation(db, attributes):
    with pytest.raises(ValidationError):
        cognito_triggers.post_confirmation(event(**attributes), None)
    assert UserRepository(db).list_all() == []


def test_email_taken_by_another_user_fails_instead_of_linking(db):
    # Alguien en la base con ese email y sin cuenta de Cognito: no se le pega este sub.
    other = UserRepository(db).create(
        User(email="ana@example.com", name="Otra Ana", role=UserRole.sysadmin)
    )
    with pytest.raises(Exception, match="already exists"):
        cognito_triggers.post_confirmation(event(), None)

    assert UserRepository(db).get(other.id).cognito_sub is None
    assert UserRepository(db).get_by_cognito_sub(SUB) is None
