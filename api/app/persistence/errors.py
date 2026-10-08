"""Errores de la capa de persistencia.

`persistence` no conoce a `services` (la dependencia apunta hacia adentro), así que no
puede levantar `ConflictError`. Levanta estos, y quien llama decide qué significan: un
service que quiere un mensaje propio los atrapa y lanza el `ConflictError` de siempre;
si nadie los atrapa, `main.py` los mapea a 409 igual que a las excepciones de dominio.
Esto cierra el riesgo de §9 del roadmap (un `ConditionalCheckFailed` mal traducido sale
como 500 donde el contrato dice 409): la traducción de boto3 pasa en un solo lugar,
`_support.run_transaction`.
"""


class PersistenceError(Exception):
    """Base de los errores que la capa de datos levanta a propósito."""


class ConditionFailedError(PersistenceError):
    """Una escritura condicional no se cumplió: el ítem cambió o no existe.

    Es la forma en que DynamoDB dice "otro request llegó primero". Reemplaza al `if` de
    un service seguido de un `commit`, que dejaba una ventana entre los dos.
    """


class AlreadyExistsError(ConditionFailedError):
    """Se intentó crear algo cuya identidad (email, nombre de género, isbn) ya existe."""
