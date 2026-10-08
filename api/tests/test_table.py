"""`persistence/table.py` contra DynamoDB Local.

Necesita DynamoDB Local (ver `dynamo_support.py`).
"""

import pytest

from app.persistence import keys
from app.persistence.table import INDEXES, TableSchemaError, ensure_table

from .dynamo_support import temporary_dynamo


@pytest.fixture()
def dynamo():
    yield from temporary_dynamo(create_table=False)


def test_ensure_table_creates_table_and_four_gsis(dynamo):
    assert ensure_table(dynamo) is True

    description = dynamo.client.describe_table(TableName=dynamo.table_name)["Table"]
    assert description["TableStatus"] == "ACTIVE"
    assert [(k["AttributeName"], k["KeyType"]) for k in description["KeySchema"]] == [
        (keys.PK, "HASH"),
        (keys.SK, "RANGE"),
    ]
    assert description["BillingModeSummary"]["BillingMode"] == "PAY_PER_REQUEST"
    assert description["StreamSpecification"] == {
        "StreamEnabled": True,
        "StreamViewType": "NEW_AND_OLD_IMAGES",
    }

    gsis = {g["IndexName"]: g for g in description["GlobalSecondaryIndexes"]}
    assert set(gsis) == {"GSI1", "GSI2", "GSI3", "GSI4"}
    for name, pk_attr, sk_attr in INDEXES:
        assert gsis[name]["IndexStatus"] == "ACTIVE"
        assert [k["AttributeName"] for k in gsis[name]["KeySchema"]] == [pk_attr, sk_attr]
        assert gsis[name]["Projection"]["ProjectionType"] == "ALL"


def test_ensure_table_is_idempotent(dynamo):
    assert ensure_table(dynamo) is True
    assert ensure_table(dynamo) is False


def test_ensure_table_rejects_a_table_with_other_indexes(dynamo):
    dynamo.client.create_table(
        TableName=dynamo.table_name,
        AttributeDefinitions=[
            {"AttributeName": keys.PK, "AttributeType": "S"},
            {"AttributeName": keys.SK, "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": keys.PK, "KeyType": "HASH"},
            {"AttributeName": keys.SK, "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    with pytest.raises(TableSchemaError, match="no migrations"):
        ensure_table(dynamo)


def test_gsi4_only_contains_open_reservations(dynamo):
    """El índice disperso: cerrar una reserva (`REMOVE GSI4PK, GSI4SK`) la saca de GSI4."""
    from datetime import datetime, timedelta, timezone

    ensure_table(dynamo)
    reserved = datetime(2026, 1, 1, tzinfo=timezone.utc)
    expires = reserved + timedelta(days=3)

    def reservation_item(reservation_id, **kwargs):
        return {
            **keys.reservation(reservation_id, 1, 2, reserved, **kwargs),
            "id": reservation_id,
        }

    dynamo.table.put_item(Item=reservation_item(1, open_until=expires))
    dynamo.table.put_item(Item=reservation_item(2, open_until=expires))

    def open_ids(bound):
        response = dynamo.table.query(
            IndexName=keys.GSI4,
            KeyConditionExpression="GSI4PK = :open AND GSI4SK < :bound",
            ExpressionAttributeValues={":open": keys.OPEN, ":bound": bound},
        )
        return sorted(int(item["id"]) for item in response["Items"])

    after_expiry = keys.expires_before(expires + timedelta(seconds=1))
    assert open_ids(after_expiry) == [1, 2]
    assert open_ids(keys.expires_before(expires)) == []  # estricto: vence a las `expires`

    dynamo.table.update_item(
        Key=keys.key(keys.reservation_pk(1)),
        UpdateExpression="REMOVE " + ", ".join(keys.GSI4_ATTRIBUTES),
    )
    assert open_ids(after_expiry) == [2]


def test_gsi2_returns_available_copies_of_a_book_grouped_by_library(dynamo):
    ensure_table(dynamo)
    isbn = "9780307474728"
    copies = [
        (1, 10, "available"),
        (2, 2, "available"),
        (3, 2, "loaned"),
        (4, 2, "available"),
        (5, 3, "lost"),
    ]
    for copy_id, library_id, status in copies:
        dynamo.table.put_item(
            Item={**keys.copy(copy_id, isbn, library_id, status), "id": copy_id}
        )
    # Un ejemplar de otro libro no tiene que colarse.
    dynamo.table.put_item(Item=keys.copy(99, "9780000000002", 2, "available"))

    response = dynamo.table.query(
        IndexName=keys.GSI2,
        KeyConditionExpression="GSI2PK = :book AND begins_with(GSI2SK, :prefix)",
        ExpressionAttributeValues={
            ":book": keys.book_pk(isbn),
            ":prefix": keys.copy_status_prefix("available"),
        },
    )
    # Agrupados por sede (2 antes que 10, por el padding) y sin prestados ni perdidos.
    assert [int(item["id"]) for item in response["Items"]] == [2, 4, 1]
