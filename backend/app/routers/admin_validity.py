"""Certificate validity per instrument type (admin only).

  GET    /api/v1/admin/validity          every instrument type with the period a new certificate gets
  PUT    /api/v1/admin/validity/{type}   give a type its own period (days)
  DELETE /api/v1/admin/validity/{type}   go back to the default period

The rules are applied by services/validity.py when a certificate is issued. They never change a
certificate that already exists. Every change is written to the audit trail.
"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.config.db import validity_rules_col
from app.middleware.auth import role_required
from app.models.instrument import ALLOWED_INSTRUMENT_TYPES
from app.models.validity import ValidityRuleIn, ValidityRuleOut, ValidityRulesOut
from app.services import audit as audit_service
from app.services import validity as validity_service

router = APIRouter(prefix="/api/v1/admin/validity", tags=["admin-validity"])

AdminRole = Annotated[dict, Depends(role_required("admin"))]


def _row(instrument_type: str, rule: dict | None) -> ValidityRuleOut:
    default = validity_service.default_days()
    days = int(rule["days"]) if rule else default
    return ValidityRuleOut(
        type=instrument_type, days=days, label=validity_service.label(days), default_days=default,
        is_default=rule is None, updated_at=rule.get("updated_at") if rule else None,
        updated_by_name=rule.get("updated_by_name") if rule else None,
    )


def _known_type(instrument_type: str) -> str:
    if instrument_type not in ALLOWED_INSTRUMENT_TYPES:
        raise HTTPException(status_code=404, detail="Unknown instrument type")
    return instrument_type


@router.get("", response_model=ValidityRulesOut)
def list_rules(current_user: AdminRole):
    stored = validity_service.rules()
    default = validity_service.default_days()
    return ValidityRulesOut(
        default_days=default, default_label=validity_service.label(default),
        min_days=validity_service.MIN_VALIDITY_DAYS, max_days=validity_service.MAX_VALIDITY_DAYS,
        items=[_row(t, stored.get(t)) for t in ALLOWED_INSTRUMENT_TYPES],
    )


@router.put("/{instrument_type}", response_model=ValidityRuleOut)
def set_rule(instrument_type: str, payload: ValidityRuleIn, request: Request, current_user: AdminRole):
    _known_type(instrument_type)
    if not validity_service.MIN_VALIDITY_DAYS <= payload.days <= validity_service.MAX_VALIDITY_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"Validity must be between {validity_service.MIN_VALIDITY_DAYS} and "
                   f"{validity_service.MAX_VALIDITY_DAYS} days.",
        )
    before = validity_service.validity_days_for(instrument_type)
    rule = validity_rules_col.find_one_and_update(
        {"type": instrument_type},
        {"$set": {
            "days": payload.days, "updated_at": datetime.now(timezone.utc), "updated_by": current_user["_id"],
            "updated_by_name": current_user.get("name") or current_user.get("email"),
        }},
        upsert=True, return_document=True,
    )
    audit_service.log_event(
        "validity_rule_changed", outcome="success", request=request,
        email=current_user.get("email"), user_id=str(current_user["_id"]), role=current_user["role"],
        detail=f"type={instrument_type} from={before} to={payload.days}",
    )
    return _row(instrument_type, rule)


@router.delete("/{instrument_type}", response_model=ValidityRuleOut)
def reset_rule(instrument_type: str, request: Request, current_user: AdminRole):
    _known_type(instrument_type)
    before = validity_service.validity_days_for(instrument_type)
    validity_rules_col.delete_one({"type": instrument_type})
    audit_service.log_event(
        "validity_rule_reset", outcome="success", request=request,
        email=current_user.get("email"), user_id=str(current_user["_id"]), role=current_user["role"],
        detail=f"type={instrument_type} from={before} to={validity_service.default_days()}",
    )
    return _row(instrument_type, None)
