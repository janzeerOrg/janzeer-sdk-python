from decimal import Decimal

import pytest

from janzeer import add_amounts, compare_amounts, format_jnz, from_scaled, is_valid_amount, normalize_amount, parse_jnz, sub_amounts, to_scaled


def test_scaling_is_exact_and_half_up():
    assert to_scaled("0.01") == 1_000_000
    assert to_scaled("1.5") == 150_000_000
    assert to_scaled("0.000000015") == 2          # ninth digit 5 rounds up
    assert to_scaled("0.000000014") == 1
    assert to_scaled("-2.5") == -250_000_000
    assert to_scaled(3) == 300_000_000
    assert to_scaled(Decimal("0.1")) == 10_000_000
    assert to_scaled("92233720368.54775807") == 9_223_372_036_854_775_807


def test_floats_are_refused_everywhere():
    for fn in (to_scaled, normalize_amount, format_jnz):
        with pytest.raises(TypeError):
            fn(0.1)
    assert is_valid_amount(0.1) is False
    with pytest.raises(TypeError):
        to_scaled(True)


def test_garbage_is_refused():
    for bad in ("", "1e3", "+1", "1.", ".5", "1,5", "abc", "0x10"):
        with pytest.raises(ValueError):
            normalize_amount(bad)
    assert is_valid_amount("1.123456789") is False and is_valid_amount("1.12345678") is True


def test_round_trip_and_arithmetic():
    assert from_scaled(150_000_000) == "1.50000000" and from_scaled(-1) == "-0.00000001"
    assert add_amounts("0.1", "0.2") == "0.30000000"          # the sum a float gets wrong
    assert sub_amounts("100000", "1.26") == "99998.74000000"
    assert compare_amounts("1.0", "1") == 0 and compare_amounts("0.09", "0.1") == -1 and compare_amounts("2", "1.99999999") == 1


def test_formatting():
    assert format_jnz("1.50000000") == "1.5 JNZ"
    assert format_jnz("1234567.5", group=True, ticker=False) == "1,234,567.5"
    assert format_jnz("1.23456789", decimals=2) == "1.23 JNZ"       # truncates, never rounds
    assert format_jnz("5", trim=False, decimals=2, ticker=False) == "5.00"
    assert parse_jnz(" 1,234.5 jnz ") == "1234.5"
