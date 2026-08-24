from lpa.public_page import format_signed


def test_format_signed_positive():
    assert format_signed(3) == "+3"


def test_format_signed_negative():
    assert format_signed(-2) == "−" + "2"


def test_format_signed_zero():
    assert format_signed(0) == "±0"
