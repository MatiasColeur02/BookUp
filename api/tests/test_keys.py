"""`persistence/keys.py` es puro: estos tests no necesitan DynamoDB."""

from datetime import datetime, timedelta, timezone

from app.persistence import keys


def test_padded_ids_sort_numerically():
    ids = [9, 10, 2, 100]
    assert sorted(ids, key=keys.pad) == [2, 9, 10, 100]


def test_fold_ignores_case_and_accents():
    assert keys.fold("Álvaro") == keys.fold("alvaro")
    assert keys.fold("Zapata") > keys.fold("Álvaro")


def test_listing_sort_key_is_alphabetical_not_by_codepoint():
    names = ["Zapata", "álvaro", "Borges", "Álvarez"]
    ordered = sorted(names, key=lambda n: keys.author(1, n)[keys.GSI1_SK])
    assert ordered == ["Álvarez", "álvaro", "Borges", "Zapata"]


def test_same_name_is_disambiguated_by_id_in_numeric_order():
    a = keys.author(9, "Ana")[keys.GSI1_SK]
    b = keys.author(10, "Ana")[keys.GSI1_SK]
    assert a < b


def test_iso_is_fixed_width_and_utc():
    naive = datetime(2026, 1, 2, 3, 4, 5)
    aware = datetime(2026, 1, 2, 0, 4, 5, tzinfo=timezone(timedelta(hours=-3)))
    assert keys.iso(naive) == "2026-01-02T03:04:05.000000Z"
    # Mismo instante que `naive`, expresado en otra zona.
    assert keys.iso(aware) == keys.iso(naive)


def test_iso_orders_chronologically_even_with_zero_microseconds():
    # `isoformat()` omite ".000000", y ahí "…:05+00:00" > "…:05.5+00:00" ordenaría mal.
    whole = datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc)
    later = whole + timedelta(milliseconds=500)
    assert keys.iso(whole) < keys.iso(later)


def test_copy_status_prefix_selects_only_that_status_in_gsi2():
    available = keys.copy(1, "9780307474728", 3, "available")[keys.GSI2_SK]
    loaned = keys.copy(2, "9780307474728", 3, "loaned")[keys.GSI2_SK]
    prefix = keys.copy_status_prefix("available")
    assert available.startswith(prefix)
    assert not loaned.startswith(prefix)


def test_available_copies_of_a_book_group_by_library():
    isbn = "9780307474728"
    items = [
        keys.copy(7, isbn, 2, "available"),
        keys.copy(8, isbn, 10, "available"),
        keys.copy(9, isbn, 2, "available"),
    ]
    ordered = sorted(items, key=lambda item: item[keys.GSI2_SK])
    assert [item[keys.PK] for item in ordered] == ["COPY#7", "COPY#9", "COPY#8"]


def test_library_copies_prefix_with_and_without_status():
    item = keys.copy(1, "9780307474728", 3, "lost")[keys.GSI3_SK]
    assert item.startswith(keys.library_copies_prefix())
    assert item.startswith(keys.library_copies_prefix("lost"))
    assert not item.startswith(keys.library_copies_prefix("available"))


def test_open_reservation_is_in_gsi4_and_closed_one_is_not():
    reserved = datetime(2026, 1, 1, tzinfo=timezone.utc)
    expires = reserved + timedelta(days=3)

    open_item = keys.reservation(5, 1, 2, reserved, open_until=expires)
    closed_item = keys.reservation(5, 1, 2, reserved)

    assert open_item[keys.GSI4_PK] == keys.OPEN
    assert keys.GSI4_PK not in closed_item and keys.GSI4_SK not in closed_item
    # Lo que `REMOVE` tiene que borrar al cerrar es exactamente lo que se escribió al abrir.
    assert set(keys.GSI4_ATTRIBUTES) <= set(open_item)


def test_expires_before_is_strict():
    now = datetime(2026, 1, 4, tzinfo=timezone.utc)
    bound = keys.expires_before(now)
    expired = keys.open_reservation_index(1, now - timedelta(seconds=1))[keys.GSI4_SK]
    exactly_now = keys.open_reservation_index(2, now)[keys.GSI4_SK]
    future = keys.open_reservation_index(3, now + timedelta(seconds=1))[keys.GSI4_SK]
    assert expired < bound
    assert not exactly_now < bound
    assert not future < bound


def test_reservations_of_a_user_and_of_a_library_sort_by_reserved_at():
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = t1 + timedelta(days=1)
    first = keys.reservation(20, 1, 2, t1)
    second = keys.reservation(3, 1, 2, t2)
    assert first[keys.GSI2_SK] < second[keys.GSI2_SK]
    assert first[keys.GSI3_SK] < second[keys.GSI3_SK]
    assert first[keys.GSI2_SK].startswith(keys.user_reservations_prefix())
    assert first[keys.GSI3_SK].startswith(keys.library_reservations_prefix())


def test_book_links_are_inverted_by_gsi2():
    link = keys.book_author("9780307474728", 4)
    assert link[keys.PK] == "BOOK#9780307474728"
    assert link[keys.SK].startswith(keys.AUTHOR_LINK_PREFIX)
    assert link[keys.GSI2_PK] == keys.author_pk(4)
    assert link[keys.GSI2_SK] == keys.book_pk("9780307474728")
