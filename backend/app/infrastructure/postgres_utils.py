from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from ..types import CustomerProfileData


def default_profile(client_name: str) -> CustomerProfileData:
    return {
        "name": client_name,
        "secondary_line": "",
        "transport": "",
        "notes": [],
        "footer_discounts": [],
        "line_discounts_by_format": {},
        "automatic_bonus_rules": [],
        "automatic_bonus_disables_line_discount": False,
        "source_count": 0,
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, bytes):
        return value
    if isinstance(value, list):
        return [serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize_value(item) for key, item in value.items()}
    return value
