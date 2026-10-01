"""Lossless JSON: the node writes coin amounts as bare JSON numbers; a float would round them."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


def loads(text: str | bytes) -> Any:
    """Parse JSON; numbers with a fraction or exponent become ``Decimal`` (exact), integers stay ``int``."""
    return json.loads(text, parse_float=Decimal)


def _default(o: Any) -> Any:
    if isinstance(o, Decimal):
        return format(o, "f")
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


def dumps(value: Any) -> str:
    """Serialize a request body. Floats are refused: an amount must be a decimal string."""
    _reject_floats(value)
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=_default)


def _reject_floats(v: Any) -> None:
    if isinstance(v, float):
        raise TypeError("floats are not allowed in a request: pass amounts as decimal strings")
    if isinstance(v, dict):
        for x in v.values():
            _reject_floats(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            _reject_floats(x)


def decimal_str(v: Any) -> str:
    """A JSON number (or numeric string) as a plain decimal string: no exponent, digits as sent."""
    if isinstance(v, bool) or v is None:
        raise ValueError(f"not a number: {v!r}")
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return format(Decimal(v), "f")
    raise ValueError(f"not a number: {v!r}")
