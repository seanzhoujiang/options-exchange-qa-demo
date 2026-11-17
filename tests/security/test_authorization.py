from decimal import Decimal
import pytest
from tests.support.test_data import ATM_CALL, ATM_PUT, CALL_MARK_PRICE, DEFAULT_QUANTITY, HTTP_TIMEOUT_SECONDS, RESTING_BUY_PRICE

pytestmark = pytest.mark.security


def _open_order(client):
    result = client.place_order(ATM_PUT, "buy", RESTING_BUY_PRICE, DEFAULT_QUANTITY)
    assert result.status_code == 200
    assert result.json()["status"] == "open"
    return result.json()


def test_other_user_cannot_read_order(alice_client, bob_client):
    order = _open_order(alice_client)
    result = bob_client.get_order(order["order_id"])
    assert result.status_code == 404
    assert result.json() == {"code": "ORDER_NOT_FOUND", "message": "订单不存在"}
    assert "alice" not in result.text and order["order_id"] not in result.text


def test_other_user_cannot_cancel_or_release_margin(alice_client, bob_client):
    order = _open_order(alice_client)
    before = alice_client.account()
    assert before.status_code == 200
    assert Decimal(before.json()["frozen"]) == Decimal("10")
    result = bob_client.cancel_order(order["order_id"])
    assert result.status_code == 404
    assert result.json() == {"code": "ORDER_NOT_FOUND", "message": "订单不存在"}
    current = alice_client.get_order(order["order_id"])
    assert current.status_code == 200
    assert current.json()["status"] == "open"
    after = alice_client.account()
    assert after.status_code == 200
    assert Decimal(after.json()["frozen"]) == Decimal("10")
    assert Decimal(after.json()["available"]) == Decimal("9990")


def test_collections_do_not_leak_other_user_records(alice_client, bob_client):
    order = _open_order(alice_client)
    result = alice_client.place_order(ATM_CALL, "sell", CALL_MARK_PRICE, DEFAULT_QUANTITY)
    assert result.status_code == 200
    assert result.json()["status"] == "filled"
    # 先建立真实持仓与订单，防止空集合使隔离断言失去意义。
    positions = alice_client.positions()
    assert positions.status_code == 200 and len(positions.json()) == 1
    for result in (bob_client.list_orders(), bob_client.positions(), bob_client.liquidations()):
        assert result.status_code == 200
        assert result.json() == []
    result = alice_client.set_mark_price(ATM_CALL, "60000")
    assert result.status_code == 200
    assert Decimal(result.json()["mark_price"]) == Decimal("60000")
    records = alice_client.liquidations()
    assert records.status_code == 200 and len(records.json()) == 1
    for result in (bob_client.list_orders(), bob_client.positions(), bob_client.liquidations()):
        assert result.status_code == 200
        assert result.json() == []
        assert "alice" not in result.text and order["order_id"] not in result.text


def test_token_identity_cannot_be_tampered_with(alice_client, bob_client, api_client):
    alice_authorization = alice_client.session.headers["Authorization"]
    api_client.session.headers["Authorization"] = alice_authorization + "tampered"
    result = api_client.account()
    assert result.status_code == 401
    assert result.json()["code"] == "UNAUTHORIZED"
    for client, expected_username in ((alice_client, "alice"), (bob_client, "bob")):
        result = client.session.get(client.base_url + "/api/account", params={"username": "bob"}, timeout=HTTP_TIMEOUT_SECONDS)
        assert result.status_code == 200
        assert result.json()["username"] == expected_username
