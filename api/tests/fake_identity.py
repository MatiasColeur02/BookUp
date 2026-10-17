"""Un User Pool de Cognito en memoria, con la misma interfaz que `app.identity`.

Igual que el `FakeSearchIndex`: los tests de controllers, trigger y seed no hablan con AWS.
`tests/test_identity.py` verifica aparte, con el `Stubber` de botocore, que `app.identity`
le pida a Cognito lo que este fake da por hecho.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from app import identity


@dataclass
class Account:
    sub: str
    email: str
    name: str
    password: str
    permanent: bool


class FakeCognito:
    def __init__(self):
        self.accounts: dict[str, Account] = {}  # por email
        self.calls: list[tuple[str, str]] = []
        # Para simular a Cognito caído en una operación puntual.
        self.down: set[str] = set()

    def _check(self, operation: str) -> None:
        if operation in self.down:
            raise identity.IdentityUnavailableError("Could not reach the identity provider")

    def create_user(self, *, email: str, name: str, temporary_password: str) -> str:
        self.calls.append(("create_user", email))
        self._check("create_user")
        if email in self.accounts:
            raise identity.UsernameExistsError("A Cognito account with that email already exists")
        if temporary_password == "rejected-by-policy":
            raise identity.InvalidPasswordError("Password does not conform to policy")
        account = Account(str(uuid.uuid4()), email, name, temporary_password, permanent=False)
        self.accounts[email] = account
        return account.sub

    def ensure_user(self, *, email: str, name: str, password: str) -> str:
        self.calls.append(("ensure_user", email))
        self._check("ensure_user")
        account = self.accounts.get(email)
        if account is None:
            account = Account(str(uuid.uuid4()), email, name, password, permanent=True)
            self.accounts[email] = account
        account.password, account.permanent = password, True
        return account.sub

    def delete_user(self, username: str) -> None:
        self.calls.append(("delete_user", username))
        self._check("delete_user")
        for email, account in list(self.accounts.items()):
            if username in (account.sub, email):
                del self.accounts[email]

    def by_sub(self, sub: str) -> Account | None:
        return next((a for a in self.accounts.values() if a.sub == sub), None)


@pytest.fixture()
def cognito(monkeypatch) -> FakeCognito:
    fake = FakeCognito()
    monkeypatch.setattr(identity, "create_user", fake.create_user)
    monkeypatch.setattr(identity, "ensure_user", fake.ensure_user)
    monkeypatch.setattr(identity, "delete_user", fake.delete_user)
    return fake
