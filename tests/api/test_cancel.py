from decimal import Decimal

import pytest

from tests.support.test_data import (
    ATM_CALL,
    CALL_MARK_PRICE,
    DEFAULT_QUANTITY,
    RESTING_BUY_PRICE,
)

pytestmark = pytest.mark.api


def test_cancel_releases_frozen_margin(alice_client):
    order_response = alice_client.place_order(
        ATM_CALL, "buy", RESTING_BUY_PRICE, DEFAULT_QUANTITY
    )
    assert order_response.status_code == 200
    order = order_response.json()
    assert order["status"] == "open"

    before_response = alice_client.account()
    assert before_response.status_code == 200
    before = before_response.json()
    assert Decimal(before["frozen"]) == Decimal("10")
    assert Decimal(before["available"]) == Decimal("9990")

    cancel_response = alice_client.cancel_order(order["order_id"])
    assert cancel_response.status_code == 200
    cancelled_order = cancel_response.json()
    assert cancelled_order["status"] == "cancelled"
    assert cancelled_order["order_id"] == order["order_id"]

    after_response = alice_client.account()
    assert after_response.status_code == 200
    after = after_response.json()
    assert Decimal(after["frozen"]) == Decimal("0")
    assert Decimal(after["available"]) == Decimal("10000")


def test_double_cancel_returns_conflict(alice_client):
    order_response = alice_client.place_order(
        ATM_CALL, "buy", RESTING_BUY_PRICE, DEFAULT_QUANTITY
    )
    assert order_response.status_code == 200
    order = order_response.json()
    assert order["status"] == "open"

    first_cancel_response = alice_client.cancel_order(order["order_id"])
    assert first_cancel_response.status_code == 200
    first_cancel = first_cancel_response.json()
    assert first_cancel["status"] == "cancelled"

    second_cancel_response = alice_client.cancel_order(order["order_id"])
    assert second_cancel_response.status_code == 409
    second_cancel = second_cancel_response.json()
    assert second_cancel["code"] == "ORDER_NOT_CANCELLABLE"
    assert isinstance(second_cancel["message"], str)


def test_filled_order_cannot_be_cancelled(alice_client):
    order_response = alice_client.place_order(
        ATM_CALL, "buy", CALL_MARK_PRICE, DEFAULT_QUANTITY
    )
    assert order_response.status_code == 200
    order = order_response.json()
    assert order["status"] == "filled"

    cancel_response = alice_client.cancel_order(order["order_id"])
    assert cancel_response.status_code == 409
    body = cancel_response.json()
    assert body["code"] == "ORDER_NOT_CANCELLABLE"
    assert isinstance(body["message"], str)


def test_nonexistent_order_returns_not_found(alice_client):
    response = alice_client.cancel_order("missing-order-id")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "ORDER_NOT_FOUND"
    assert isinstance(body["message"], str)

