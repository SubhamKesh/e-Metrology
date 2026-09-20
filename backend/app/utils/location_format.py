from app.config.db import states_col, districts_col


def format_location(location: dict | None) -> str | None:
    """{'state_code': 'WB', 'district_code': '319', 'address_line': 'Baharampur'}
    -> 'Baharampur, Murshidabad, West Bengal'

    Falls back to the raw code if a state/district lookup misses (e.g. a
    code that predates a districts.csv refresh) rather than dropping that
    part of the address silently.
    """
    if not location:
        return None
    state = states_col.find_one({"code": location.get("state_code")})
    district = districts_col.find_one({"code": location.get("district_code"), "state_code": location.get("state_code")})
    parts = [
        location.get("address_line"),
        district["name"] if district else location.get("district_code"),
        state["name"] if state else location.get("state_code"),
    ]
    return ", ".join(p for p in parts if p)