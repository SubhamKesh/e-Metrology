from bson import ObjectId

from app.routers.applications import _normalize_id, _matches_user_id


def test_normalize_id_handles_objectid_and_string_values():
    user_id = ObjectId()
    assert _normalize_id(user_id) == str(user_id)
    assert _normalize_id(str(user_id)) == str(user_id)
    assert _normalize_id(None) is None


def test_matches_user_id_works_with_mixed_objectid_string_types():
    user_id = ObjectId()
    assert _matches_user_id(user_id, str(user_id)) is True
    assert _matches_user_id(str(user_id), user_id) is True
    assert _matches_user_id(user_id, ObjectId()) is False


def test_matches_user_id_handles_owner_and_officer_ids_consistently():
    owner_id = ObjectId()
    assert _matches_user_id(owner_id, str(owner_id)) is True
    assert _matches_user_id(str(owner_id), owner_id) is True
