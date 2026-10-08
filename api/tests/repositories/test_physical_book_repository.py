import pytest

from app.persistence.dynamo_repositories import (
    PhysicalBookRepository,
    ReservationRepository,
)
from app.persistence.entities import PhysicalBook, PhysicalBookStatus
from app.persistence.errors import ConditionFailedError

from .conftest import ISBN

OTHER = "9780000000002"
available, reserved, loaned, lost = (
    PhysicalBookStatus.available,
    PhysicalBookStatus.reserved,
    PhysicalBookStatus.loaned,
    PhysicalBookStatus.lost,
)


def ids(copies):
    return [c.id for c in copies]


def test_create_copies_the_title_and_the_library_into_the_copy(db, make):
    make.book(title="Ficciones")
    library = make.library("Sur", city="La Plata")

    copy = PhysicalBookRepository(db).create(PhysicalBook(isbn=ISBN, library_id=library.id))

    assert copy.id == 1 and copy.status is available and copy.open_reservation_id is None
    assert (copy.book_title, copy.library_name, copy.library_city) == ("Ficciones", "Sur", "La Plata")
    assert PhysicalBookRepository(db).get(copy.id) == copy
    assert PhysicalBookRepository(db).get(99) is None


def test_create_ignores_denormalized_values_the_caller_made_up(db, make):
    make.book(title="Real")
    library = make.library("Real", city="Real")
    copy = PhysicalBookRepository(db).create(
        PhysicalBook(isbn=ISBN, library_id=library.id, book_title="Falso", library_city="Falso")
    )
    assert (copy.book_title, copy.library_city) == ("Real", "Real")


def test_create_requires_an_existing_book_and_library(db, make):
    repo = PhysicalBookRepository(db)
    library = make.library()
    with pytest.raises(ConditionFailedError, match="Book"):
        repo.create(PhysicalBook(isbn=ISBN, library_id=library.id))

    make.book()
    with pytest.raises(ConditionFailedError, match="Library"):
        repo.create(PhysicalBook(isbn=ISBN, library_id=999))
    assert repo.list_all() == []


def test_list_all_without_filters_returns_every_copy_by_id(db, make):
    make.book()
    make.book(OTHER, "Otro")
    created = [make.copy(), make.copy(OTHER), make.copy()]
    assert ids(PhysicalBookRepository(db).list_all()) == ids(created)


def test_list_all_filters(db, make):
    make.book()
    make.book(OTHER, "Otro")
    sur, norte = make.library("Sur"), make.library("Norte")
    a = make.copy(ISBN, sur)
    b = make.copy(ISBN, norte)
    c = make.copy(OTHER, sur)
    d = make.copy(ISBN, sur)
    repo = PhysicalBookRepository(db)
    repo.update_status(d.id, lost)

    assert ids(repo.list_all(isbn=ISBN)) == [a.id, b.id, d.id]
    assert ids(repo.list_all(library_id=sur.id)) == [a.id, c.id, d.id]
    assert ids(repo.list_all(isbn=ISBN, library_id=sur.id)) == [a.id, d.id]
    assert ids(repo.list_all(status=lost)) == [d.id]
    assert ids(repo.list_all(status=available)) == [a.id, b.id, c.id]
    assert ids(repo.list_all(isbn=ISBN, status=available)) == [a.id, b.id]
    assert ids(repo.list_all(library_id=sur.id, status=available)) == [a.id, c.id]
    assert ids(repo.list_all(isbn=ISBN, library_id=sur.id, status=lost)) == [d.id]
    assert repo.list_all(isbn="9780000000000") == []


def test_mark_lost_and_back_to_available_moves_the_copy_between_indexes(db, make):
    make.book()
    copy = make.copy()
    repo = PhysicalBookRepository(db)

    assert repo.update_status(copy.id, lost).status is lost
    assert repo.get(copy.id).status is lost
    assert repo.list_all(isbn=ISBN, status=available) == []
    assert repo.available_by_book(ISBN) == []

    assert repo.update_status(copy.id, available).status is available
    assert ids(repo.list_all(isbn=ISBN, status=available)) == [copy.id]
    assert len(repo.available_by_book(ISBN)) == 1


def test_marking_lost_twice_is_idempotent(db, make):
    make.book()
    copy = make.copy()
    repo = PhysicalBookRepository(db)
    repo.update_status(copy.id, lost)
    assert repo.update_status(copy.id, lost).status is lost


def test_only_lost_and_available_are_manual_destinations(db, make):
    make.book()
    copy = make.copy()
    with pytest.raises(ValueError):
        PhysicalBookRepository(db).update_status(copy.id, reserved)
    with pytest.raises(ConditionFailedError):
        PhysicalBookRepository(db).update_status(404, lost)


def test_a_held_copy_cannot_be_released_by_hand(db, make):
    make.book()
    copy = make.copy()
    make.reservation(copy)

    with pytest.raises(ConditionFailedError, match="reserved"):
        PhysicalBookRepository(db).update_status(copy.id, available)

    assert PhysicalBookRepository(db).get(copy.id).status is reserved


def test_marking_lost_a_copy_with_a_pending_reservation_cancels_it(db, make):
    make.book()
    copy = make.copy()
    reservation = make.reservation(copy)

    lost_copy = PhysicalBookRepository(db).update_status(copy.id, lost)

    assert lost_copy.status is lost and lost_copy.open_reservation_id is None
    closed = ReservationRepository(db).get(reservation.id)
    assert closed.cancelled_at is not None and closed.returned_at is None
    assert not closed.is_open
    assert ReservationRepository(db).list_expired(closed.expires_at.replace(year=3000)) == []


def test_marking_lost_a_copy_that_is_out_closes_the_reservation_as_returned(db, make):
    make.book()
    copy = make.copy()
    reservation = make.reservation(copy)
    ReservationRepository(db).mark_picked_up(reservation.id)

    PhysicalBookRepository(db).update_status(copy.id, lost)

    closed = ReservationRepository(db).get(reservation.id)
    assert closed.returned_at is not None and closed.cancelled_at is None
    assert ReservationRepository(db).list_all(is_open=True) == []


def test_delete_and_has_reservations(db, make):
    make.book()
    repo = PhysicalBookRepository(db)
    clean, used = make.copy(), make.copy()
    assert repo.has_reservations(clean.id) is False

    reservation = make.reservation(used)
    assert repo.has_reservations(used.id) is True
    # También cuenta si la reserva ya se cerró: el historial se conserva.
    ReservationRepository(db).cancel(reservation.id)
    assert repo.has_reservations(used.id) is True

    repo.delete(clean)
    assert repo.get(clean.id) is None


def test_available_by_book_groups_by_library_and_skips_unavailable_copies(db, make):
    make.book()
    make.book(OTHER, "Otro")
    sur, norte = make.library("Sur"), make.library("Norte")
    a1, a2 = make.copy(ISBN, sur), make.copy(ISBN, sur)
    b1 = make.copy(ISBN, norte)
    held, gone = make.copy(ISBN, norte), make.copy(ISBN, norte)
    make.copy(OTHER, sur)  # otro libro
    make.reservation(held)
    PhysicalBookRepository(db).update_status(gone.id, lost)

    grouped = PhysicalBookRepository(db).available_by_book(ISBN)

    by_name = {library.name: ids(copies) for library, copies in grouped}
    assert by_name == {"Sur": [a1.id, a2.id], "Norte": [b1.id]}
    assert {library.id for library, _ in grouped} == {sur.id, norte.id}
    # La sede viene completa (dirección, ciudad...), no solo el nombre.
    assert all(library.address and library.city for library, _ in grouped)
    assert PhysicalBookRepository(db).available_by_book("9780000000000") == []


def test_available_by_book_reflects_a_reservation_immediately(db, make):
    make.book()
    copy = make.copy()
    repo = PhysicalBookRepository(db)
    assert len(repo.available_by_book(ISBN)) == 1

    reservation = make.reservation(copy)
    assert repo.available_by_book(ISBN) == []

    ReservationRepository(db).cancel(reservation.id)
    assert len(repo.available_by_book(ISBN)) == 1
