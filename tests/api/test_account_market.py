from decimal import Decimal
import pytest
from tests.support.test_data import ATM_CALL, INSTRUMENT_NAMES, UNKNOWN_INSTRUMENT

pytestmark = pytest.mark.api


def test_seed_account_values(alice_client):
    result = alice_client.account()
    assert result.status_code == 200
    account = result.json()
    assert account["username"] == "alice"
    assert account["status"] == "active"
    for field in ("balance", "available", "equity"):
        assert isinstance(account[field], str)
        assert Decimal(account[field]) == Decimal("10000")
    for field in ("frozen", "maintenance_margin"):
        assert Decimal(account[field]) == Decimal("0")


def test_instruments_have_seed_fields(api_client):
    result = api_client.instruments()
    assert result.status_code == 200
    instruments = result.json()
    assert len(instruments) == 4
    assert {instrument["name"] for instrument in instruments} == set(INSTRUMENT_NAMES)
    expected = [("100000", "call", "5000"), ("100000", "put", "4800"),
                ("110000", "call", "2000"), ("90000", "put", "1500")]
    for name, (strike, option_type, mark) in zip(INSTRUMENT_NAMES, expected):
        instrument = next(item for item in instruments if item["name"] == name)
        assert instrument["underlying"] == "BTC"
        assert instrument["expiry"] == "2026-12-31T08:00:00Z"
        assert instrument["option_type"] == option_type
        assert isinstance(instrument["strike"], str) and isinstance(instrument["mark_price"], str)
        assert Decimal(instrument["strike"]) == Decimal(strike)
        assert Decimal(instrument["mark_price"]) == Decimal(mark)


@pytest.mark.parametrize("instrument,status", [(ATM_CALL, 200), (UNKNOWN_INSTRUMENT, 404)])
def test_ticker_contract(api_client, instrument, status):
    result = api_client.ticker(instrument)
    assert result.status_code == status
    if status == 404:
        assert result.json()["code"] == "INSTRUMENT_NOT_FOUND"
    else:
        assert result.json()["instrument"] == instrument
        assert Decimal(result.json()["mark_price"]) == Decimal("5000")
        assert Decimal(result.json()["index_price"]) == Decimal("100000")
