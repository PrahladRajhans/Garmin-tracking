from datetime import date

import pytest

from garmin_mcp.client import parse_date


def test_parse_date_default_is_today():
    assert parse_date(None) == date.today().isoformat()


def test_parse_date_valid():
    assert parse_date("2026-01-05") == "2026-01-05"


def test_parse_date_rejects_garbage():
    with pytest.raises(ValueError):
        parse_date("05/01/2026")
