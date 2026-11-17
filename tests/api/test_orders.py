from decimal import Decimal

import pytest

from tests.support.test_data import (
    MAX_PRICE, MAX_QUANTITY, PRICE_TICK, QUANTITY_STEP, MIN_QUANTITY,
    ATM_CALL,
    ATM_PUT,
    CALL_MARK_PRICE,
    DEFAULT_QUANTITY,
    OTM_CALL,
    OTM_PUT,
    RESTING_BUY_PRICE,
    UNKNOWN_INSTRUMENT,
)

pytestmark = pytest.mark.api


def test_resting_buy_freezes_required_margin(alice_client):
    response = alice_client.place_order(
        ATM_CALL, "buy", RESTING_BUY_PRICE, DEFAULT_QUANTITY
    )

    assert response.status_code == 200
    order = response.json()
    assert order["status"] == "open"
    assert order["side"] == "buy"
    assert order["instrument"] == ATM_CALL
    assert Decimal(order["required"]) == Decimal("10")

    account_response = alice_client.account()
    assert account_response.status_code == 200
    account = account_response.json()
    assert Decimal(account["balance"]) == Decimal("10000")
    assert Decimal(account["frozen"]) == Decimal("10")
    assert Decimal(account["available"]) == Decimal("9990")


@pytest.mark.parametrize("limit_price", ["5000", "5500"])
def test_filled_buy_debits_premium_and_opens_long_position(
    limit_price, alice_client
):
    response = alice_client.place_order(
        ATM_CALL, "buy", limit_price, DEFAULT_QUANTITY
    )

    assert response.status_code == 200
    order = response.json()
    assert order["status"] == "filled"
    assert order["side"] == "buy"
    assert Decimal(order["fill_price"]) == Decimal("5000")

    account_response = alice_client.account()
    assert account_response.status_code == 200
    account = account_response.json()
    assert Decimal(account["balance"]) == Decimal("9500")
    assert Decimal(account["available"]) == Decimal("9500")
    assert Decimal(account["equity"]) == Decimal("10000")

    positions_response = alice_client.positions()
    assert positions_response.status_code == 200
    positions = positions_response.json()
    assert len(positions) == 1
    assert positions[0]["instrument"] == ATM_CALL
    assert Decimal(positions[0]["quantity"]) == Decimal("0.1")
    assert Decimal(positions[0]["average_price"]) == Decimal("5000")


def test_filled_sell_credits_premium_and_opens_short_position(alice_client):
    response = alice_client.place_order(
        ATM_CALL, "sell", CALL_MARK_PRICE, DEFAULT_QUANTITY
    )

    assert response.status_code == 200
    order = response.json()
    assert order["status"] == "filled"
    assert order["side"] == "sell"
    assert Decimal(order["fill_price"]) == Decimal("5000")

    account_response = alice_client.account()
    assert account_response.status_code == 200
    account = account_response.json()
    assert Decimal(account["balance"]) == Decimal("10500")
    assert Decimal(account["available"]) == Decimal("8500")
    assert Decimal(account["equity"]) == Decimal("10000")

    positions_response = alice_client.positions()
    assert positions_response.status_code == 200
    positions = positions_response.json()
    assert len(positions) == 1
    assert positions[0]["instrument"] == ATM_CALL
    assert Decimal(positions[0]["quantity"]) == Decimal("-0.1")


@pytest.mark.parametrize(
    ("price", "expected_status", "expected_order_status", "expected_code"),
    [
        ("0", 400, None, "INVALID_PARAM"),
        ("-0.5", 400, None, "INVALID_PARAM"),
        (str(PRICE_TICK / Decimal("2")), 400, None, "INVALID_PARAM"),
        (str(PRICE_TICK), 200, "open", None),
        (str(MAX_PRICE), 200, "filled", None),
        ("100.3", 400, None, "INVALID_PARAM"),
        (str(MAX_PRICE + PRICE_TICK), 400, None, "INVALID_PARAM"),
        ("not-a-number", 400, None, "INVALID_PARAM"),
    ],
)
def test_price_boundaries(
    price, expected_status, expected_order_status, expected_code, alice_client
):
    if price == str(MAX_PRICE):
        seed_buy_response = alice_client.place_order(
            ATM_CALL, "buy", CALL_MARK_PRICE, DEFAULT_QUANTITY
        )
        assert seed_buy_response.status_code == 200
        assert seed_buy_response.json()["status"] == "filled"

        mark_response = alice_client.set_mark_price(ATM_CALL, str(MAX_PRICE))
        assert mark_response.status_code == 200
        mark_body = mark_response.json()
        assert mark_body["instrument"] == ATM_CALL
        assert Decimal(mark_body["mark_price"]) == MAX_PRICE

        # 用低于市价的卖单价格关掉多仓，按 1,000,000 成交并回收盈利；平多部分不占空头保证金。
        profit_sell_response = alice_client.place_order(
            ATM_CALL, "sell", CALL_MARK_PRICE, DEFAULT_QUANTITY
        )
        assert profit_sell_response.status_code == 200
        profit_sell = profit_sell_response.json()
        assert profit_sell["status"] == "filled"
        assert Decimal(profit_sell["fill_price"]) == MAX_PRICE

    response = alice_client.place_order(
        ATM_CALL, "buy", price, DEFAULT_QUANTITY
    )

    assert response.status_code == expected_status
    body = response.json()
    if expected_status == 200:
        assert body["status"] == expected_order_status
        assert Decimal(body["price"]) == Decimal(price)
    else:
        assert body["code"] == expected_code
        assert body["field"] == "price"
        assert isinstance(body["message"], str)


@pytest.mark.parametrize(
    ("quantity", "expected_status", "expected_code"),
    [
        ("0", 400, "INVALID_PARAM"),
        ("0.15", 400, "INVALID_PARAM"),
        (str(MIN_QUANTITY), 200, None),
        (str(MAX_QUANTITY), 200, None),
        (str(MAX_QUANTITY + QUANTITY_STEP), 400, "INVALID_PARAM"),
    ],
)
def test_quantity_boundaries(
    quantity, expected_status, expected_code, alice_client
):
    # 0.5 × 100 = 50，最大数量边界也在初始余额内且低于触发成交价。
    response = alice_client.place_order(ATM_CALL, "buy", "0.5", quantity)

    assert response.status_code == expected_status
    body = response.json()
    if expected_status == 200:
        assert body["status"] == "open"
        assert Decimal(body["quantity"]) == Decimal(quantity)
    else:
        assert body["code"] == expected_code
        assert body["field"] == "quantity"
        assert isinstance(body["message"], str)


def test_invalid_side_returns_parameter_error(alice_client):
    response = alice_client.place_order(
        ATM_CALL, "hold", RESTING_BUY_PRICE, DEFAULT_QUANTITY
    )

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INVALID_PARAM"
    assert body["field"] == "side"


def test_unknown_instrument_returns_not_found(alice_client):
    response = alice_client.place_order(
        UNKNOWN_INSTRUMENT, "buy", RESTING_BUY_PRICE, DEFAULT_QUANTITY
    )

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "INSTRUMENT_NOT_FOUND"
    assert body["field"] == "instrument"


def test_insufficient_margin_rejects_order(alice_client):
    response = alice_client.place_order(ATM_CALL, "buy", "5000", "3")

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "INSUFFICIENT_MARGIN"
    assert isinstance(body["message"], str)


def test_order_status_filter_returns_matching_orders(alice_client):
    open_response = alice_client.place_order(
        ATM_CALL, "buy", RESTING_BUY_PRICE, DEFAULT_QUANTITY
    )
    assert open_response.status_code == 200
    open_order = open_response.json()
    assert open_order["status"] == "open"

    filled_response = alice_client.place_order(
        ATM_PUT, "buy", CALL_MARK_PRICE, DEFAULT_QUANTITY
    )
    assert filled_response.status_code == 200
    filled_order = filled_response.json()
    assert filled_order["status"] == "filled"

    open_list_response = alice_client.list_orders(status="open")
    assert open_list_response.status_code == 200
    open_orders = open_list_response.json()
    assert [order["order_id"] for order in open_orders] == [open_order["order_id"]]
    assert all(order["status"] == "open" for order in open_orders)

    filled_list_response = alice_client.list_orders(status="filled")
    assert filled_list_response.status_code == 200
    filled_orders = filled_list_response.json()
    assert [order["order_id"] for order in filled_orders] == [filled_order["order_id"]]
    assert all(order["status"] == "filled" for order in filled_orders)

    invalid_status_response = alice_client.list_orders(status="unknown")
    assert invalid_status_response.status_code == 400
    invalid_status = invalid_status_response.json()
    assert invalid_status["code"] == "INVALID_PARAM"
    assert invalid_status["field"] == "status"

