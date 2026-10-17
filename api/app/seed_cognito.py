"""Crea en el User Pool de Cognito las cuentas de los usuarios sembrados (`COGNITO_ROADMAP.md` §5.4).

    python -m app.seed_cognito

Va **después** de `python -m app.seed`, que no cambia: siembra DynamoDB y no sabe de Cognito.
Esto recorre los `User` que todavía no tienen `cognito_sub` y, por cada uno, se asegura de que
exista su cuenta (sin email de invitación y con el email ya verificado: los `@bookup.example`
no existen), le pone la contraseña del seed como **permanente** —las cuentas de demo entran
directo, sin cambio obligatorio— y vincula el `sub`.

Idempotente: un usuario ya vinculado se saltea, y una cuenta que ya existía en Cognito (una
corrida anterior que se cortó antes de vincular) se reusa en vez de duplicarse. Si las
credenciales del lab vencen a mitad, volver a correrlo termina el trabajo.

Lee el pool de `COGNITO_USER_POOL_ID` y la tabla de `DYNAMO_TABLE`; contra la tabla real, sin
`DYNAMO_ENDPOINT_URL`. Son ~32 usuarios: un bucle secuencial alcanza.
"""

from __future__ import annotations

from . import identity
from .config import settings
from .persistence.dynamo import Dynamo, get_dynamo
from .persistence.repositories import UserRepository
from .seed import SEED_PASSWORD


def seed_cognito(db: Dynamo | None = None, *, password: str = SEED_PASSWORD) -> int:
    """Vincula cada usuario sin `cognito_sub` con su cuenta. Devuelve cuántos vinculó."""
    if not settings.cognito_user_pool_id:
        raise SystemExit("COGNITO_USER_POOL_ID is not set: which User Pool should I seed?")
    db = db or get_dynamo()
    repo = UserRepository(db)

    pending = [u for u in repo.list_all() if u.cognito_sub is None]
    for user in pending:
        sub = identity.ensure_user(email=user.email, name=user.name, password=password)
        repo.set_cognito_sub(user.id, sub)
        print(f"  {user.email} → linked")

    print(f"Linked {len(pending)} users to Cognito (pool {settings.cognito_user_pool_id}).")
    if pending:
        print(f"They log in with the password {password!r}.")
    return len(pending)


if __name__ == "__main__":
    seed_cognito()
