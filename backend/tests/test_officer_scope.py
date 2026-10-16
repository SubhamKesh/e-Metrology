"""LMO = district-level, GATC = state-level."""
from app.middleware.auth import jurisdiction_filter
from app.services import notifications as n


def test_lmo_without_district_sees_nothing():
    lmo = {"role": "lmo", "jurisdiction": {"state_code": "WB", "district_code": None}}
    assert jurisdiction_filter(lmo)["district_code"] == "__no_district_assigned__"


def test_lmo_with_district_scoped_to_it():
    lmo = {"role": "lmo", "jurisdiction": {"state_code": "WB", "district_code": "319"}}
    assert jurisdiction_filter(lmo) == {"state_code": "WB", "district_code": "319"}


def test_gatc_is_state_wide():
    gatc = {"role": "gatc", "jurisdiction": {"state_code": "WB", "district_code": None}}
    assert jurisdiction_filter(gatc) == {"state_code": "WB"}


def test_lmo_without_district_gets_no_notifications():
    audience = {"state_code": "WB", "district_code": "319"}
    lmo = {"role": "lmo", "user_id": "u", "state_code": "WB", "district_code": None}
    gatc = {**lmo, "role": "gatc"}
    assert not n._should_deliver(lmo, audience)
    assert n._should_deliver(gatc, audience)
