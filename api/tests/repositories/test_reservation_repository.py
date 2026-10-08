import threading
from datetime import datetime, timedelta, timezone

import pytest

from app.persistence.repositories import PhysicalBookRepository, ReservationRepository
from app.persistence.entities import PhysicalBookStatus, Reservation
from app.persistence.errors import ConditionFailedError

from ..factories import ISBN

available, reserved, loaned = (
    PhysicalBookStatus.available,
    PhysicalBookStatus.reserved,
    PhysicalBookStatus.loaned,
)


def now():
    return datetime.now(timezone.utc)


def status_of(db, copy):
    return PhysicalBookRepository(db).get(copy.id).status


@pytest.fixture()
def setup(db, make):
    make.book()
    return make


# -- create -------------------------------------------------------------


def test_create_reserves_the_copy_and_denormalizes_library_and_isbn(db, setup):
    library = setup.library()
    copy = setup.copy(library=library)
    user = setup.user()

    reservation = setup.reservation(copy, user)

    assert reservation.id == 1 and reservation.picked_up is False and reservation.is_open
    assert (reservation.library_id, reservation.isbn) == (library.id, ISBN)
    assert reservation.reserved_at is not None
    assert ReservationRepository(db).get(reservation.id) == reservation

    stored_copy = PhysicalBookRepository(db).get(copy.id)
    assert stored_copy.status is reserved and stored_copy.open_reservation_id == reservation.id


def test_create_on_an_unavailable_copy_is_a_conflict_and_writes_nothing(db, setup):
    copy = setup.copy()
    setup.reservation(copy)

    with pytest.raises(ConditionFailedError, match="not available"):
        setup.reservation(copy)

    assert len(ReservationRepository(db).list_all()) == 1


def test_create_on_a_missing_copy(db, setup):
    with pytest.raises(ConditionFailedError, match="does not exist"):
        ReservationRepository(db).create(
            Reservation(user_id=1, physical_book_id=404, expires_at=now() + timedelta(days=1))
        )


def test_create_ignores_state_the_caller_tries_to_smuggle_in(db, setup):
    copy = setup.copy()
    forged = Reservation(
        user_id=setup.user().id,
        physical_book_id=copy.id,
        expires_at=now() + timedelta(days=1),
        picked_up=True,
        returned_at=now(),
        library_id=999,
    )
    created = ReservationRepository(db).create(forged)
    assert created.picked_up is False and created.returned_at is None and created.is_open
    assert created.library_id == copy.library_id


def test_two_simultaneous_reservations_of_the_same_copy_one_wins(db, setup):
    copy = setup.copy()
    users = [setup.user() for _ in range(8)]
    outcomes, barrier = [], threading.Barrier(8)

    def reserve(user):
        barrier.wait()
        try:
            outcomes.append(setup.reservation(copy, user))
        except ConditionFailedError as exc:
            outcomes.append(exc)

    threads = [threading.Thread(target=reserve, args=(u,)) for u in users]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    winners = [o for o in outcomes if isinstance(o, Reservation)]
    losers = [o for o in outcomes if isinstance(o, ConditionFailedError)]
    assert len(winners) == 1 and len(losers) == 7
    assert len(ReservationRepository(db).list_all(is_open=True)) == 1
    assert PhysicalBookRepository(db).get(copy.id).open_reservation_id == winners[0].id


# -- lecturas -----------------------------------------------------------


def test_get_missing(db):
    assert ReservationRepository(db).get(404) is None


def test_list_all_filters(db, setup):
    sur, norte = setup.library("Sur"), setup.library("Norte")
    ana, bruno = setup.user(), setup.user()
    r1 = setup.reservation(setup.copy(library=sur), ana)
    r2 = setup.reservation(setup.copy(library=norte), ana)
    r3 = setup.reservation(setup.copy(library=sur), bruno)
    repo = ReservationRepository(db)
    repo.cancel(r2.id)

    def ids(**kw):
        return [r.id for r in repo.list_all(**kw)]

    assert ids() == [r1.id, r2.id, r3.id]
    assert ids(user_id=ana.id) == [r1.id, r2.id]
    assert ids(library_id=sur.id) == [r1.id, r3.id]
    assert ids(user_id=ana.id, library_id=sur.id) == [r1.id]
    assert ids(is_open=True) == [r1.id, r3.id]
    assert ids(is_open=False) == [r2.id]
    assert ids(user_id=ana.id, is_open=True) == [r1.id]
    assert ids(user_id=ana.id, is_open=False) == [r2.id]
    assert ids(library_id=sur.id, is_open=False) == []
    assert ids(library_id=norte.id, is_open=False) == [r2.id]
    assert ids(user_id=999) == []


def test_get_open_for_physical_book(db, setup):
    copy = setup.copy()
    repo = ReservationRepository(db)
    assert repo.get_open_for_physical_book(copy.id) is None
    assert repo.get_open_for_physical_book(404) is None

    reservation = setup.reservation(copy)
    assert repo.get_open_for_physical_book(copy.id) == reservation

    repo.cancel(reservation.id)
    assert repo.get_open_for_physical_book(copy.id) is None


# -- transiciones -------------------------------------------------------


def test_pickup_marks_the_copy_as_loaned(db, setup):
    copy = setup.copy()
    reservation = setup.reservation(copy)

    picked = ReservationRepository(db).mark_picked_up(reservation.id)

    assert picked.picked_up is True and picked.is_open
    assert ReservationRepository(db).get(reservation.id).picked_up is True
    assert status_of(db, copy) is loaned


def test_pickup_twice_or_after_closing_is_a_conflict(db, setup):
    repo = ReservationRepository(db)
    picked = setup.reservation()
    repo.mark_picked_up(picked.id)
    with pytest.raises(ConditionFailedError):
        repo.mark_picked_up(picked.id)

    cancelled = setup.reservation()
    repo.cancel(cancelled.id)
    with pytest.raises(ConditionFailedError):
        repo.mark_picked_up(cancelled.id)


def test_cancel_releases_the_copy_and_leaves_the_open_index(db, setup):
    copy = setup.copy()
    reservation = setup.reservation(copy, )
    repo = ReservationRepository(db)
    assert [r.id for r in repo.list_all(is_open=True)] == [reservation.id]

    cancelled = repo.cancel(reservation.id)

    assert cancelled.cancelled_at is not None and cancelled.returned_at is None
    assert not cancelled.is_open
    stored_copy = PhysicalBookRepository(db).get(copy.id)
    assert stored_copy.status is available and stored_copy.open_reservation_id is None
    assert repo.list_all(is_open=True) == []
    assert repo.list_expired(now() + timedelta(days=30)) == []
    # El historial se conserva.
    assert repo.get(reservation.id).cancelled_at is not None


def test_cancel_after_pickup_is_a_conflict(db, setup):
    reservation = setup.reservation()
    repo = ReservationRepository(db)
    repo.mark_picked_up(reservation.id)
    with pytest.raises(ConditionFailedError):
        repo.cancel(reservation.id)


def test_cancel_twice_is_a_conflict(db, setup):
    reservation = setup.reservation()
    repo = ReservationRepository(db)
    repo.cancel(reservation.id)
    with pytest.raises(ConditionFailedError):
        repo.cancel(reservation.id)


def test_return_requires_pickup_and_releases_the_copy(db, setup):
    copy = setup.copy()
    reservation = setup.reservation(copy)
    repo = ReservationRepository(db)

    with pytest.raises(ConditionFailedError):
        repo.mark_returned(reservation.id)  # nunca se retiró

    repo.mark_picked_up(reservation.id)
    returned = repo.mark_returned(reservation.id)

    assert returned.returned_at is not None and returned.cancelled_at is None
    assert status_of(db, copy) is available
    assert repo.list_all(is_open=True) == []
    with pytest.raises(ConditionFailedError):
        repo.mark_returned(reservation.id)


def test_a_returned_copy_can_be_reserved_again(db, setup):
    copy = setup.copy()
    first = setup.reservation(copy)
    repo = ReservationRepository(db)
    repo.mark_picked_up(first.id)
    repo.mark_returned(first.id)

    second = setup.reservation(copy)

    assert second.id != first.id and status_of(db, copy) is reserved
    assert PhysicalBookRepository(db).has_reservations(copy.id)


def test_transitions_on_missing_reservations(db):
    repo = ReservationRepository(db)
    for call in (repo.mark_picked_up, repo.cancel, repo.mark_returned):
        with pytest.raises(ConditionFailedError, match="does not exist"):
            call(404)
    with pytest.raises(ConditionFailedError):
        repo.update_expiry(404, now())


def test_update_expiry_moves_the_reservation_in_the_expiry_index(db, setup):
    reservation = setup.reservation(expires_in=timedelta(days=1))
    repo = ReservationRepository(db)
    in_two_days = now() + timedelta(days=2)
    assert repo.list_expired(in_two_days) == [repo.get(reservation.id)]

    extended = repo.update_expiry(reservation.id, now() + timedelta(days=10))

    assert extended.expires_at > in_two_days
    assert repo.get(reservation.id).expires_at == extended.expires_at
    assert repo.list_expired(in_two_days) == []
    assert [r.id for r in repo.list_expired(now() + timedelta(days=11))] == [reservation.id]


def test_update_expiry_after_pickup_or_closing_is_a_conflict(db, setup):
    repo = ReservationRepository(db)
    picked = setup.reservation()
    repo.mark_picked_up(picked.id)
    with pytest.raises(ConditionFailedError):
        repo.update_expiry(picked.id, now() + timedelta(days=5))

    cancelled = setup.reservation()
    repo.cancel(cancelled.id)
    with pytest.raises(ConditionFailedError):
        repo.update_expiry(cancelled.id, now() + timedelta(days=5))


# -- vencimientos -------------------------------------------------------


def test_list_expired_only_returns_open_overdue_unpicked_reservations(db, setup):
    repo = ReservationRepository(db)
    overdue = setup.reservation(expires_in=timedelta(hours=1))
    fresh = setup.reservation(expires_in=timedelta(days=5))
    picked = setup.reservation(expires_in=timedelta(hours=1))
    repo.mark_picked_up(picked.id)
    cancelled = setup.reservation(expires_in=timedelta(hours=1))
    repo.cancel(cancelled.id)

    expired = repo.list_expired(now() + timedelta(days=1))

    assert [r.id for r in expired] == [overdue.id]
    assert fresh.id not in [r.id for r in expired]


def test_expire_releases_the_copies_and_is_idempotent(db, setup):
    repo = ReservationRepository(db)
    copies = [setup.copy() for _ in range(3)]
    reservations = [setup.reservation(c, expires_in=timedelta(hours=1)) for c in copies]
    when = now() + timedelta(days=1)

    assert repo.expire([r.id for r in repo.list_expired(when)], when) == 3

    assert all(status_of(db, c) is available for c in copies)
    assert all(repo.get(r.id).cancelled_at is not None for r in reservations)
    assert repo.list_expired(when) == []
    assert repo.expire([r.id for r in reservations], when) == 0  # segunda corrida: nada


def test_expire_handles_more_reservations_than_a_transaction_holds(db, setup):
    repo = ReservationRepository(db)
    library = setup.library()
    reservations = [
        setup.reservation(setup.copy(library=library), expires_in=timedelta(hours=1))
        for _ in range(120)
    ]
    when = now() + timedelta(days=1)
    assert len(repo.list_expired(when)) == 120

    assert repo.expire([r.id for r in reservations], when) == 120

    assert repo.list_expired(when) == []
    assert repo.list_all(is_open=True) == []
    assert len(PhysicalBookRepository(db).list_all(status=available)) == 120


def test_expire_skips_the_ones_that_changed_and_still_expires_the_rest(db, setup):
    repo = ReservationRepository(db)
    a, b, c = (setup.reservation(expires_in=timedelta(hours=1)) for _ in range(3))
    when = now() + timedelta(days=1)
    stale = [a.id, b.id, c.id]
    repo.cancel(b.id)  # entre el listado y el vencimiento, alguien la canceló
    picked_copy = PhysicalBookRepository(db).get(a.physical_book_id)
    assert picked_copy.status is reserved

    assert repo.expire(stale, when) == 2

    assert repo.get(a.id).cancelled_at is not None and repo.get(c.id).cancelled_at is not None
    assert repo.get(b.id).cancelled_at != when  # conserva su propia fecha


def test_expire_does_not_touch_a_reservation_that_was_picked_up_meanwhile(db, setup):
    repo = ReservationRepository(db)
    keep, drop = (setup.reservation(expires_in=timedelta(hours=1)) for _ in range(2))
    ids = [keep.id, drop.id]
    repo.mark_picked_up(keep.id)

    assert repo.expire(ids, now() + timedelta(days=1)) == 1

    assert repo.get(keep.id).is_open and repo.get(keep.id).picked_up
    assert PhysicalBookRepository(db).get(keep.physical_book_id).status is loaned
    assert PhysicalBookRepository(db).get(drop.physical_book_id).status is available
