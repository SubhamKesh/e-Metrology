"""
Who may receive a real-time notification (services/notifications.py).

Pure logic plus fake sockets -- no Redis, no database, no running server.
These pin down the rule that a notification about one owner's application
in one district must not reach other owners or officers of other
jurisdictions, and that anything ambiguous fails closed.
"""
import asyncio

from app.services import notifications as n

AUDIENCE = {"owner_id": "owner-1", "state_code": "WB", "district_code": "319"}


def ident(role, user_id="u", state=None, district=None):
    return {"user_id": user_id, "role": role, "state_code": state, "district_code": district}


def test_admin_receives_everything_even_without_an_audience():
    assert n._should_deliver(ident("admin"), AUDIENCE)
    assert n._should_deliver(ident("admin"), None)


def test_owner_receives_only_their_own_records():
    assert n._should_deliver(ident("owner", "owner-1"), AUDIENCE)
    assert not n._should_deliver(ident("owner", "owner-2"), AUDIENCE)


def test_district_officer_receives_only_their_district():
    assert n._should_deliver(ident("lmo", state="WB", district="319"), AUDIENCE)
    assert not n._should_deliver(ident("lmo", state="WB", district="315"), AUDIENCE)
    assert not n._should_deliver(ident("lmo", state="KA", district="319"), AUDIENCE)


def test_state_level_officer_receives_any_district_in_their_state():
    assert n._should_deliver(ident("gatc", state="WB", district=None), AUDIENCE)
    assert not n._should_deliver(ident("gatc", state="KA", district=None), AUDIENCE)


def test_officer_named_in_the_audience_receives_it_regardless_of_jurisdiction():
    audience = {**AUDIENCE, "officer_id": "officer-9"}
    assert n._should_deliver(ident("lmo", "officer-9", state="KA", district="1"), audience)
    assert not n._should_deliver(ident("lmo", "officer-8", state="KA", district="1"), audience)


def test_officer_with_no_jurisdiction_receives_nothing():
    assert not n._should_deliver(ident("lmo", state=None, district=None), AUDIENCE)


def test_no_audience_reaches_admins_only():
    assert not n._should_deliver(ident("owner", "owner-1"), None)
    assert not n._should_deliver(ident("lmo", state="WB", district="319"), None)
    assert not n._should_deliver(ident("gatc", state="WB"), {})


def test_unknown_role_receives_nothing():
    assert not n._should_deliver(ident("stranger", "owner-1", state="WB", district="319"), AUDIENCE)


class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send_text(self, data):
        self.sent.append(data)


def test_local_broadcast_delivers_only_to_allowed_connections(monkeypatch):
    mine, other_owner, wrong_district, admin = FakeSocket(), FakeSocket(), FakeSocket(), FakeSocket()
    monkeypatch.setattr(
        n,
        "_clients",
        {
            mine: ident("owner", "owner-1"),
            other_owner: ident("owner", "owner-2"),
            wrong_district: ident("lmo", state="WB", district="315"),
            admin: ident("admin"),
        },
    )

    asyncio.run(n.local_broadcast({"type": "application_submitted"}, AUDIENCE))

    assert len(mine.sent) == 1
    assert len(admin.sent) == 1
    assert other_owner.sent == []
    assert wrong_district.sent == []


def test_local_broadcast_serializes_datetimes(monkeypatch):
    from datetime import datetime, timezone

    sock = FakeSocket()
    monkeypatch.setattr(n, "_clients", {sock: ident("admin")})

    asyncio.run(n.local_broadcast({"at": datetime(2026, 9, 27, tzinfo=timezone.utc)}, None))

    assert "2026-09-27T00:00:00+00:00" in sock.sent[0]
