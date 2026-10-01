"""Native-coin amounts.

Amounts cross this SDK as decimal STRINGS (``"1.5"``, ``"0.01"``) and are scaled to an integer of base units exactly
the way the node's ``ByteUtils.toScaledLong`` does. A binary floating-point number is refused everywhere: ``0.1`` is
not representable, and money must not depend on how a float prints.
"""

from __future__ import annotations

import re
from decimal import Decimal

from .constants import DECIMALS, TICKER

_SCALE = 10**DECIMALS
_DECIMAL_RE = re.compile(r"^-?(\d+)(?:\.(\d+))?$")

#: Amount input accepted everywhere: a decimal string (preferred), an ``int`` of whole coins, or a ``Decimal``.
AmountLike = str | int | Decimal


def normalize_amount(amount: AmountLike) -> str:
    """Canonical decimal string: no exponent, no ``+``, digits as given. Raises ``ValueError`` on anything else."""
    if isinstance(amount, bool) or isinstance(amount, float):
        raise TypeError("amounts are decimal strings, ints or Decimals — never floats")
    if isinstance(amount, int):
        return str(amount)
    if isinstance(amount, Decimal):
        if not amount.is_finite():
            raise ValueError(f"not a finite amount: {amount!r}")
        s = format(amount, "f")
    elif isinstance(amount, str):
        s = amount.strip()
    else:
        raise TypeError(f"unsupported amount type: {type(amount).__name__}")
    if not _DECIMAL_RE.match(s):
        raise ValueError(f"not a decimal amount: {amount!r}")
    return s


def is_valid_amount(amount: AmountLike) -> bool:
    """True for a plain decimal with at most 8 fractional digits (what the node accepts)."""
    try:
        s = normalize_amount(amount)
    except (TypeError, ValueError):
        return False
    return len(s.partition(".")[2]) <= DECIMALS


def to_scaled(amount: AmountLike) -> int:
    """``BigDecimal(amount).setScale(8, HALF_UP) x 10^8`` as an integer. Pinned by the vectors' ``scaled`` table."""
    s = normalize_amount(amount)
    neg = s.startswith("-")
    int_part, _, frac_part = (s[1:] if neg else s).partition(".")
    frac8 = (frac_part + "0" * DECIMALS)[:DECIMALS]
    scaled = int(int_part or "0") * _SCALE + int(frac8)
    if len(frac_part) > DECIMALS and frac_part[DECIMALS] >= "5":  # HALF_UP on the first dropped digit
        scaled += 1
    return -scaled if neg else scaled


def from_scaled(scaled: int) -> str:
    """Inverse of :func:`to_scaled`: base units -> decimal string with exactly 8 fractional digits."""
    if isinstance(scaled, bool) or not isinstance(scaled, int):
        raise TypeError("base units are an int")
    neg = scaled < 0
    whole, frac = divmod(-scaled if neg else scaled, _SCALE)
    return f"{'-' if neg else ''}{whole}.{frac:0{DECIMALS}d}"


def format_jnz(amount: AmountLike, *, decimals: int = DECIMALS, trim: bool = True, ticker: bool = True, group: bool = False) -> str:
    """Human-readable amount: ``format_jnz("1.50000000")`` -> ``"1.5 JNZ"``. Truncates (never rounds) beyond ``decimals``."""
    s = normalize_amount(amount)
    neg = s.startswith("-")
    whole, _, frac = (s[1:] if neg else s).partition(".")
    frac = frac[:decimals]
    frac = frac.rstrip("0") if trim else frac.ljust(decimals, "0")
    if group:
        whole = f"{int(whole):,}"
    out = f"{'-' if neg else ''}{whole}{'.' + frac if frac else ''}"
    return f"{out} {TICKER}" if ticker else out


def parse_jnz(text: str) -> str:
    """Parse user input like ``"1,234.5 JNZ"`` into a canonical amount string (``"1234.5"``)."""
    cleaned = re.sub(rf"\s*{TICKER}\s*$", "", text, flags=re.IGNORECASE).replace(",", "").strip()
    return normalize_amount(cleaned)


def compare_amounts(a: AmountLike, b: AmountLike) -> int:
    """Exact comparison: -1, 0 or 1."""
    x, y = to_scaled(a), to_scaled(b)
    return (x > y) - (x < y)


def add_amounts(a: AmountLike, b: AmountLike) -> str:
    """Exact ``a + b`` as a canonical 8-decimal string."""
    return from_scaled(to_scaled(a) + to_scaled(b))


def sub_amounts(a: AmountLike, b: AmountLike) -> str:
    """Exact ``a - b`` as a canonical 8-decimal string."""
    return from_scaled(to_scaled(a) - to_scaled(b))
