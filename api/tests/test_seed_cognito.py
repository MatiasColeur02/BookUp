"""`python -m app.seed_cognito` con Cognito en memoria."""

import pytest

from app import seed as seeding
from app.config import settings
from app.persistence.repositories import UserRepository
from app.seed_cognito import seed_cognito

from .fake_identity import cognito  # noqa: F401  (fixture)


@pytest.fixture()
def seeded(db, monkeypatch):
    seeding.seed(db)
    monkeypatch.setattr(settings, "cognito_user_pool_id", "us-east-1_TestPool")
    return db


def test_every_seeded_user_gets_an_account_and_is_linked(seeded, cognito):
    users = UserRepository(seeded).list_all()

    assert seed_cognito(seeded) == len(users)

    for user in UserRepository(seeded).list_all():
        account = cognito.accounts[user.email]
        assert user.cognito_sub == account.sub
        # Las cuentas de demo entran directo con la contraseña del README.
        assert (account.password, account.permanent) == (seeding.SEED_PASSWORD, True)


def test_running_it_twice_duplicates_nothing(seeded, cognito):
    seed_cognito(seeded)
    accounts = {email: a.sub for email, a in cognito.accounts.items()}
    calls = len(cognito.calls)

    assert seed_cognito(seeded) == 0

    assert {email: a.sub for email, a in cognito.accounts.items()} == accounts
    assert len(cognito.calls) == calls  # ni siquiera vuelve a llamar a Cognito


def test_an_interrupted_run_is_finished_by_the_next_one(seeded, cognito, monkeypatch):
    real = cognito.ensure_user
    done = []

    def expiring(**kwargs):
        if len(done) == 5:  # vencen las credenciales del lab
            raise RuntimeError("ExpiredToken")
        done.append(kwargs["email"])
        return real(**kwargs)

    monkeypatch.setattr("app.identity.ensure_user", expiring)
    with pytest.raises(RuntimeError):
        seed_cognito(seeded)
    monkeypatch.setattr("app.identity.ensure_user", real)

    users = UserRepository(seeded).list_all()
    assert seed_cognito(seeded) == len(users) - 5
    assert all(u.cognito_sub for u in UserRepository(seeded).list_all())
    assert len(cognito.accounts) == len(users)


def test_an_account_left_unlinked_is_reused(seeded, cognito):
    # Una corrida anterior creó la cuenta en Cognito y se cortó antes de vincularla.
    admin = UserRepository(seeded).get_by_email("admin@bookup.example")
    existing = cognito.ensure_user(email=admin.email, name=admin.name, password="otra")

    seed_cognito(seeded)

    assert UserRepository(seeded).get(admin.id).cognito_sub == existing
    assert cognito.accounts[admin.email].password == seeding.SEED_PASSWORD


def test_without_a_pool_it_refuses_to_run(seeded, cognito, monkeypatch):
    monkeypatch.setattr(settings, "cognito_user_pool_id", "")
    with pytest.raises(SystemExit, match="COGNITO_USER_POOL_ID"):
        seed_cognito(seeded)
    assert cognito.calls == []
