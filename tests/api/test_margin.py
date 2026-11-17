from decimal import Decimal

import pytest

from tests.support.test_data import (
    ATM_CALL,
    CALL_MARK_PRICE,
    DEFAULT_QUANTITY,
    OTM_CALL,
    OTM_PUT,
)

pytestmark = pytest.mark.api


@pytest.mark.parametrize(
    ("instrument", "price", "expected_required", "expected_available"),
    [
        # ATM 看涨：((15% × 100000) + 5500) × 0.1 = 2050；可用额为 10000 - 2050。
        (ATM_CALL, "5500", "2050", "7950"),
        # OTM 看涨：max(15000 - 10000, 10000) 加权利金后乘 0.1，保证金为 1250。
        (OTM_CALL, "2500", "1250", "8750"),
        # OTM 看跌：max(15000 - 10000, 10000) 加权利金后乘 0.1，保证金为 1200。
        (OTM_PUT, "2000", "1200", "8800"),
    ],
)
def test_resting_short_orders_reserve_expected_margin(
    instrument, price, expected_required, expected_available, alice_client
):
    response = alice_client.place_order(
        instrument, "sell", price, DEFAULT_QUANTITY
    )

    assert response.status_code == 200
    order = response.json()
    assert order["status"] == "open"
    assert order["side"] == "sell"
    assert Decimal(order["required"]) == Decimal(expected_required)

    account_response = alice_client.account()
    assert account_response.status_code == 200
    account = account_response.json()
    assert Decimal(account["balance"]) == Decimal("10000")
    assert Decimal(account["frozen"]) == Decimal(expected_required)
    assert Decimal(account["available"]) == Decimal(expected_available)


def test_filled_atm_short_tracks_balance_margin_and_equity(alice_client):
    response = alice_client.place_order(
        ATM_CALL, "sell", CALL_MARK_PRICE, DEFAULT_QUANTITY
    )

    assert response.status_code == 200
    order = response.json()
    assert order["status"] == "filled"
    assert Decimal(order["fill_price"]) == Decimal("5000")

    account_response = alice_client.account()
    assert account_response.status_code == 200
    account = account_response.json()
    # 成交收取 500 权利金，ATM 空头保证金为 (15000 + 5000) × 0.1 = 2000。
    assert Decimal(account["balance"]) == Decimal("10500")
    assert Decimal(account["available"]) == Decimal("8500")
    assert Decimal(account["equity"]) == Decimal("10000")

    positions_response = alice_client.positions()
    assert positions_response.status_code == 200
    positions = positions_response.json()
    assert len(positions) == 1
    assert positions[0]["instrument"] == ATM_CALL
    assert Decimal(positions[0]["quantity"]) == Decimal("-0.1")
    assert Decimal(positions[0]["average_price"]) == Decimal("5000")

