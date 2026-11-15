import threading
from datetime import datetime, timedelta, timezone

import pytest

from app.persistence.repositories import PhysicalBookRepository, ReservationRepository
from app.persistence.entities import (
    SEED_ORIGIN,
    CancelledBy,
    CloseReason,
    DeadlineKind,
    PhysicalBookStatus,
    Reservation,
)
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


# -- historial: close_reason, cancelled_by, picked_up_at -------------------
# Lo que necesitan las notificaciones (`notifications-roadmap.md` §5.1) para distinguir
# vencida de cancelada y perdida de devuelta.


def test_create_starts_with_no_history_even_if_the_caller_sends_one(db, setup):
    forged = Reservation(
        user_id=setup.user().id,
        physical_book_id=setup.copy().id,
        expires_at=now() + timedelta(days=1),
        close_reason=CloseReason.returned,
        cancelled_by=CancelledBy.library,
        picked_up_at=now(),
        pickup_deadline_notified_at=now(),
        return_deadline_notified_at=now(),
        origin=SEED_ORIGIN,
    )
    created = ReservationRepository(db).create(forged)
    stored = ReservationRepository(db).get(created.id)
    for reservation in (created, stored):
        assert reservation.close_reason is None and reservation.cancelled_by is None
        assert reservation.picked_up_at is None and reservation.origin is None
        assert reservation.pickup_deadline_notified_at is None
        assert reservation.return_deadline_notified_at is None


def test_pickup_records_when(db, setup):
    reservation = setup.reservation()
    at = now()

    picked = ReservationRepository(db).mark_picked_up(reservation.id, at)

    assert picked.picked_up_at == at
    assert ReservationRepository(db).get(reservation.id).picked_up_at == at


def test_pickup_without_a_time_uses_now(db, setup):
    reservation = setup.reservation()
    before = now()
    picked = ReservationRepository(db).mark_picked_up(reservation.id)
    assert picked.picked_up_at >= before
    assert ReservationRepository(db).get(reservation.id).picked_up_at == picked.picked_up_at


@pytest.mark.parametrize("by", [CancelledBy.user, CancelledBy.library, None])
def test_cancel_records_reason_and_who(db, setup, by):
    reservation = setup.reservation()

    cancelled = ReservationRepository(db).cancel(reservation.id, by=by)

    stored = ReservationRepository(db).get(reservation.id)
    for r in (cancelled, stored):
        assert r.close_reason is CloseReason.cancelled and r.cancelled_by is by


def test_return_records_the_reason(db, setup):
    reservation = setup.reservation()
    repo = ReservationRepository(db)
    repo.mark_picked_up(reservation.id)

    returned = repo.mark_returned(reservation.id)

    stored = repo.get(reservation.id)
    for r in (returned, stored):
        assert r.close_reason is CloseReason.returned and r.cancelled_by is None


def test_expire_records_expired_not_cancelled(db, setup):
    repo = ReservationRepository(db)
    expiring = setup.reservation(expires_in=timedelta(hours=1))
    cancelled = setup.reservation(expires_in=timedelta(hours=1))
    repo.cancel(cancelled.id, by=CancelledBy.user)
    when = now() + timedelta(days=1)

    assert repo.expire([expiring.id, cancelled.id], when) == 1

    stored = repo.get(expiring.id)
    assert stored.cancelled_at == when and stored.close_reason is CloseReason.expired
    assert stored.cancelled_by is None
    assert repo.get(cancelled.id).close_reason is CloseReason.cancelled  # no la pisa


def test_expire_in_bulk_records_expired_on_every_one(db, setup):
    repo = ReservationRepository(db)
    reservations = [setup.reservation(expires_in=timedelta(hours=1)) for _ in range(3)]
    assert repo.expire([r.id for r in reservations], now() + timedelta(days=1)) == 3
    assert all(repo.get(r.id).close_reason is CloseReason.expired for r in reservations)


@pytest.mark.parametrize("picked_up, column", [(False, "cancelled_at"), (True, "returned_at")])
def test_losing_the_copy_records_lost_whether_pending_or_loaned(db, setup, picked_up, column):
    copy = setup.copy()
    reservation = setup.reservation(copy)
    repo = ReservationRepository(db)
    if picked_up:
        repo.mark_picked_up(reservation.id)

    PhysicalBookRepository(db).update_status(copy.id, PhysicalBookStatus.lost)

    stored = repo.get(reservation.id)
    assert getattr(stored, column) is not None and not stored.is_open
    assert stored.close_reason is CloseReason.lost and stored.cancelled_by is None
    assert status_of(db, copy) is PhysicalBookStatus.lost


# -- vencimientos que avisa el job -----------------------------------------


def test_list_past_due_returns_open_overdue_reservations_picked_up_or_not(db, setup):
    repo = ReservationRepository(db)
    pending = setup.reservation(expires_in=timedelta(hours=1))
    loaned = setup.reservation(expires_in=timedelta(hours=1))
    repo.mark_picked_up(loaned.id)
    setup.reservation(expires_in=timedelta(days=5))  # todavía en plazo
    closed = setup.reservation(expires_in=timedelta(hours=1))
    repo.cancel(closed.id)
    returned = setup.reservation(expires_in=timedelta(hours=1))
    repo.mark_picked_up(returned.id)
    repo.mark_returned(returned.id)

    past_due = repo.list_past_due(now() + timedelta(days=1))

    assert [r.id for r in past_due] == [pending.id, loaned.id]
    assert [r.picked_up for r in past_due] == [False, True]
    # `list_expired` sigue viendo solo las sin retirar.
    assert [r.id for r in repo.list_expired(now() + timedelta(days=1))] == [pending.id]


@pytest.mark.parametrize(
    "kind, picked_up, mark",
    [
        (DeadlineKind.pickup, False, "pickup_deadline_notified_at"),
        (DeadlineKind.return_, True, "return_deadline_notified_at"),
    ],
)
def test_mark_deadline_notified_sets_the_mark_once(db, setup, kind, picked_up, mark):
    repo = ReservationRepository(db)
    reservation = setup.reservation(expires_in=timedelta(hours=1))
    if picked_up:
        repo.mark_picked_up(reservation.id)
    at = now() + timedelta(days=1)

    marked = repo.mark_deadline_notified(reservation.id, kind, reservation.expires_at, at)

    assert getattr(marked, mark) == at
    assert getattr(repo.get(reservation.id), mark) == at
    # Segunda corrida del job: la marca ya está, no se vuelve a avisar.
    with pytest.raises(ConditionFailedError):
        repo.mark_deadline_notified(reservation.id, kind, reservation.expires_at, at)
    assert getattr(repo.get(reservation.id), mark) == at


def test_mark_deadline_notified_requires_the_matching_state(db, setup):
    repo = ReservationRepository(db)
    pending = setup.reservation(expires_in=timedelta(hours=1))
    loaned = setup.reservation(expires_in=timedelta(hours=1))
    repo.mark_picked_up(loaned.id)
    closed = setup.reservation(expires_in=timedelta(hours=1))
    repo.cancel(closed.id)

    with pytest.raises(ConditionFailedError):  # sin retirar no hay devolución que avisar
        repo.mark_deadline_notified(pending.id, DeadlineKind.return_, pending.expires_at)
    with pytest.raises(ConditionFailedError):  # ya retirada: el retiro no vence
        repo.mark_deadline_notified(loaned.id, DeadlineKind.pickup, loaned.expires_at)
    with pytest.raises(ConditionFailedError):  # cerrada
        repo.mark_deadline_notified(closed.id, DeadlineKind.pickup, closed.expires_at)
    with pytest.raises(ConditionFailedError, match="does not exist|no pickup"):
        repo.mark_deadline_notified(404, DeadlineKind.pickup, now())

    assert repo.get(pending.id).return_deadline_notified_at is None
    assert repo.get(loaned.id).pickup_deadline_notified_at is None


def test_mark_deadline_notified_loses_the_race_against_an_extension(db, setup):
    """El job listó la reserva vencida; antes de marcarla, la sede extendió el plazo. La
    condición sobre `expires_at` evita avisar un vencimiento que ya no existe."""
    repo = ReservationRepository(db)
    reservation = setup.reservation(expires_in=timedelta(hours=1))
    seen = repo.list_past_due(now() + timedelta(days=1))[0]

    repo.update_expiry(reservation.id, now() + timedelta(days=10))

    with pytest.raises(ConditionFailedError):
        repo.mark_deadline_notified(seen.id, DeadlineKind.pickup, seen.expires_at)
    assert repo.get(reservation.id).pickup_deadline_notified_at is None


def test_extending_removes_the_pickup_mark_so_the_next_expiry_notifies_again(db, setup):
    repo = ReservationRepository(db)
    reservation = setup.reservation(expires_in=timedelta(hours=1))
    repo.mark_deadline_notified(reservation.id, DeadlineKind.pickup, reservation.expires_at)
    assert repo.get(reservation.id).pickup_deadline_notified_at is not None

    new_expiry = now() + timedelta(days=2)
    extended = repo.update_expiry(reservation.id, new_expiry)

    assert extended.pickup_deadline_notified_at is None
    assert repo.get(reservation.id).pickup_deadline_notified_at is None
    # Vence de nuevo: se puede volver a marcar, con el nuevo `expires_at`.
    again = repo.mark_deadline_notified(reservation.id, DeadlineKind.pickup, new_expiry)
    assert again.pickup_deadline_notified_at is not None


def test_extending_without_a_mark_still_works(db, setup):
    repo = ReservationRepository(db)
    reservation = setup.reservation()
    extended = repo.update_expiry(reservation.id, now() + timedelta(days=5))
    assert extended.pickup_deadline_notified_at is None
