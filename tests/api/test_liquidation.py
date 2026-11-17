from decimal import Decimal
import pytest
from tests.support.test_data import ATM_CALL, ATM_PUT, CALL_MARK_PRICE, DEFAULT_QUANTITY, RESTING_BUY_PRICE

pytestmark = pytest.mark.api


@pytest.fixture
def short_client(alice_client):
    result = alice_client.place_order(ATM_CALL, "sell", CALL_MARK_PRICE, DEFAULT_QUANTITY)
    assert result.status_code == 200
    assert result.json()["status"] == "filled"
    return alice_client


def test_price_rise_below_threshold_keeps_account_active(short_client):
    result = short_client.set_mark_price(ATM_CALL, "10000")
    assert result.status_code == 200
    assert Decimal(result.json()["mark_price"]) == Decimal("10000")
    result = short_client.account()
    assert result.status_code == 200
    account = result.json()
    # 现金 10500，持仓市值 -1000，权益 9500；维持保证金 (7500+10000)*0.1=1750。
    assert account["status"] == "active"
    assert Decimal(account["balance"]) == Decimal("10500")
    assert Decimal(account["equity"]) == Decimal("9500")
    assert Decimal(account["maintenance_margin"]) == Decimal("1750")
    result = short_client.liquidations()
    assert result.status_code == 200
    assert result.json() == []


def test_liquidation_closes_positions_and_cancels_orders(short_client):
    resting = short_client.place_order(ATM_PUT, "buy", RESTING_BUY_PRICE, DEFAULT_QUANTITY)
    assert resting.status_code == 200
    assert resting.json()["status"] == "open"
    result = short_client.set_mark_price(ATM_CALL, "60000")
    assert result.status_code == 200
    assert Decimal(result.json()["mark_price"]) == Decimal("60000")
    result = short_client.account()
    assert result.status_code == 200
    account = result.json()
    # 10500-60000*0.1=4500，小于 (7500+60000)*0.1=6750。
    assert account["status"] == "liquidated"
    assert Decimal(account["balance"]) == Decimal("4500")
    assert Decimal(account["equity"]) == Decimal("4500")
    assert Decimal(account["frozen"]) == Decimal("0")
    positions = short_client.positions()
    assert positions.status_code == 200
    assert positions.json() == []
    order = short_client.get_order(resting.json()["order_id"])
    assert order.status_code == 200
    assert order.json()["status"] == "cancelled"
    records = short_client.liquidations()
    assert records.status_code == 200
    assert len(records.json()) == 1
    record = records.json()[0]
    assert record["time"]
    assert Decimal(record["equity_before"]) == Decimal("4500")
    assert Decimal(record["maintenance_margin"]) == Decimal("6750")
    assert Decimal(record["shortfall"]) == Decimal("0")
    assert len(record["positions_closed"]) == 1
    assert record["positions_closed"][0]["instrument"] == ATM_CALL
    assert Decimal(record["positions_closed"][0]["quantity"]) == Decimal("-0.1")


def test_deep_loss_floors_balance_and_records_shortfall(short_client):
    result = short_client.set_mark_price(ATM_CALL, "200000")
    assert result.status_code == 200
    assert Decimal(result.json()["mark_price"]) == Decimal("200000")
    result = short_client.account()
    assert result.status_code == 200
    assert result.json()["status"] == "liquidated"
    assert Decimal(result.json()["balance"]) == Decimal("0")
    records = short_client.liquidations()
    assert records.status_code == 200
    assert len(records.json()) == 1
    # 10500-200000*0.1=-9500，归零后缺口为9500。
    assert Decimal(records.json()[0]["equity_before"]) == Decimal("-9500")
    assert Decimal(records.json()[0]["shortfall"]) == Decimal("9500")


def test_liquidated_account_cannot_place_order(short_client):
    result = short_client.set_mark_price(ATM_CALL, "60000")
    assert result.status_code == 200
    assert Decimal(result.json()["mark_price"]) == Decimal("60000")
    result = short_client.place_order(ATM_CALL, "buy", RESTING_BUY_PRICE, DEFAULT_QUANTITY)
    assert result.status_code == 403
    assert result.json()["code"] == "ACCOUNT_LIQUIDATED"


def test_liquidation_does_not_affect_other_user(short_client, bob_client):
    result = short_client.set_mark_price(ATM_CALL, "60000")
    assert result.status_code == 200
    assert Decimal(result.json()["mark_price"]) == Decimal("60000")
    result = bob_client.account()
    assert result.status_code == 200
    assert result.json()["status"] == "active"
    assert Decimal(result.json()["balance"]) == Decimal("10000")
    assert Decimal(result.json()["equity"]) == Decimal("10000")
    records = bob_client.liquidations()
    assert records.status_code == 200
    assert records.json() == []
