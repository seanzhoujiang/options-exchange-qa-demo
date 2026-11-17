from decimal import Decimal

import pytest

from tests.support.test_data import (
    ATM_CALL,
    ATM_PUT,
    CALL_MARK_PRICE,
    DEFAULT_QUANTITY,
    OTM_CALL,
    RESTING_BUY_PRICE,
)

pytestmark = pytest.mark.api


def test_close_long_needs_no_short_margin(alice_client):
    long_order = alice_client.place_order(ATM_CALL, "buy", CALL_MARK_PRICE, "1.9")
    assert long_order.status_code == 200
    assert long_order.json()["status"] == "filled"
    assert Decimal(long_order.json()["fill_price"]) == Decimal("5000")

    before = alice_client.account()
    assert before.status_code == 200
    assert Decimal(before.json()["balance"]) == Decimal("500")
    assert Decimal(before.json()["available"]) == Decimal("500")

    # 卖出数量完全平掉已有多仓，不会形成空头，因此无需空头保证金。
    close_order = alice_client.place_order(ATM_CALL, "sell", CALL_MARK_PRICE, "1.9")
    assert close_order.status_code == 200
    assert close_order.json()["status"] == "filled"
    assert Decimal(close_order.json()["required"]) == Decimal("0")
    assert Decimal(close_order.json()["fill_price"]) == Decimal("5000")

    after = alice_client.account()
    assert after.status_code == 200
    assert Decimal(after.json()["balance"]) == Decimal("10000")
    assert Decimal(after.json()["equity"]) == Decimal("10000")
    positions = alice_client.positions()
    assert positions.status_code == 200
    assert positions.json() == []


def test_short_margin_only_on_excess_sell(alice_client):
    result = alice_client.place_order(ATM_CALL, "buy", "5000", "0.1")
    assert result.status_code == 200
    assert result.json()["status"] == "filled"
    result = alice_client.place_order(ATM_CALL, "sell", "5000", "0.2")
    assert result.status_code == 200
    # 先平 0.1 多仓，仅新增 0.1 空仓：(15000+5000)*0.1=2000。
    assert result.json()["status"] == "filled"
    assert Decimal(result.json()["required"]) == Decimal("2000")
    positions = alice_client.positions()
    assert positions.status_code == 200
    assert Decimal(positions.json()[0]["quantity"]) == Decimal("-0.1")


def test_liquidation_preserves_bob_account(alice_client, bob_client):
    alice_order = alice_client.place_order(ATM_PUT, "buy", RESTING_BUY_PRICE, DEFAULT_QUANTITY)
    assert alice_order.status_code == 200
    assert alice_order.json()["status"] == "open"

    bob_before = bob_client.account()
    assert bob_before.status_code == 200
    assert Decimal(bob_before.json()["available"]) == Decimal("10000")

    bob_order = bob_client.place_order(ATM_PUT, "buy", RESTING_BUY_PRICE, DEFAULT_QUANTITY)
    assert bob_order.status_code == 200
    assert bob_order.json()["status"] == "open"
    bob_with_order = bob_client.account()
    assert bob_with_order.status_code == 200
    assert Decimal(bob_with_order.json()["frozen"]) == Decimal("10")
    assert Decimal(bob_with_order.json()["available"]) == Decimal("9990")

    short_order = alice_client.place_order(ATM_CALL, "sell", CALL_MARK_PRICE, DEFAULT_QUANTITY)
    assert short_order.status_code == 200
    assert short_order.json()["status"] == "filled"
    mark_update = alice_client.set_mark_price(ATM_CALL, "60000")
    assert mark_update.status_code == 200
    assert Decimal(mark_update.json()["mark_price"]) == Decimal("60000")

    alice_account = alice_client.account()
    assert alice_account.status_code == 200
    assert alice_account.json()["status"] == "liquidated"
    alice_cancelled_order = alice_client.get_order(alice_order.json()["order_id"])
    assert alice_cancelled_order.status_code == 200
    assert alice_cancelled_order.json()["status"] == "cancelled"

    bob_still_open = bob_client.get_order(bob_order.json()["order_id"])
    assert bob_still_open.status_code == 200
    assert bob_still_open.json()["status"] == "open"
    bob_after = bob_client.account()
    assert bob_after.status_code == 200
    assert Decimal(bob_after.json()["balance"]) == Decimal("10000")
    assert Decimal(bob_after.json()["frozen"]) == Decimal("10")
    assert Decimal(bob_after.json()["available"]) == Decimal("9990")


def test_liquidate_mixed_positions(alice_client):
    long_order = alice_client.place_order(ATM_PUT, "buy", "4800", DEFAULT_QUANTITY)
    assert long_order.status_code == 200
    assert long_order.json()["status"] == "filled"
    short_order = alice_client.place_order(ATM_CALL, "sell", CALL_MARK_PRICE, DEFAULT_QUANTITY)
    assert short_order.status_code == 200
    assert short_order.json()["status"] == "filled"

    # 余额为 10000-480+500=10020；标记市值为 480-6000，清算前权益为 4500。
    # 空头维持保证金为 (7500+60000)*0.1=6750，故触发清算。
    mark_update = alice_client.set_mark_price(ATM_CALL, "60000")
    assert mark_update.status_code == 200
    assert Decimal(mark_update.json()["mark_price"]) == Decimal("60000")

    account = alice_client.account()
    assert account.status_code == 200
    assert account.json()["status"] == "liquidated"
    assert Decimal(account.json()["balance"]) == Decimal("4500")
    records = alice_client.liquidations()
    assert records.status_code == 200
    assert len(records.json()) == 1
    record = records.json()[0]
    assert Decimal(record["equity_before"]) == Decimal("4500")
    assert Decimal(record["maintenance_margin"]) == Decimal("6750")
    assert Decimal(record["shortfall"]) == Decimal("0")
    closed_positions = record["positions_closed"]
    assert len(closed_positions) == 2
    quantities_by_instrument = {position["instrument"]: Decimal(position["quantity"]) for position in closed_positions}
    assert quantities_by_instrument == {ATM_PUT: Decimal("0.1"), ATM_CALL: Decimal("-0.1")}
    positions = alice_client.positions()
    assert positions.status_code == 200
    assert positions.json() == []


def test_netting_average_and_pnl(alice_client):
    first_buy = alice_client.place_order(ATM_CALL, "buy", "5000", DEFAULT_QUANTITY)
    assert first_buy.status_code == 200
    assert first_buy.json()["status"] == "filled"
    initial_positions = alice_client.positions()
    assert initial_positions.status_code == 200
    initial = initial_positions.json()[0]
    assert Decimal(initial["quantity"]) == Decimal("0.1")
    assert Decimal(initial["average_price"]) == Decimal("5000")
    assert Decimal(initial["unrealized_pnl"]) == Decimal("0")
    first_mark = alice_client.set_mark_price(ATM_CALL, "6000")
    assert first_mark.status_code == 200
    assert Decimal(first_mark.json()["mark_price"]) == Decimal("6000")
    marked_positions = alice_client.positions()
    assert marked_positions.status_code == 200
    marked = marked_positions.json()[0]
    assert Decimal(marked["quantity"]) == Decimal("0.1")
    assert Decimal(marked["average_price"]) == Decimal("5000")
    assert Decimal(marked["unrealized_pnl"]) == Decimal("100")

    second_buy = alice_client.place_order(ATM_CALL, "buy", "6000", DEFAULT_QUANTITY)
    assert second_buy.status_code == 200
    assert second_buy.json()["status"] == "filled"
    position_response = alice_client.positions()
    assert position_response.status_code == 200
    position = position_response.json()[0]
    assert Decimal(position["quantity"]) == Decimal("0.2")
    assert Decimal(position["average_price"]) == Decimal("5500")
    # 两份持仓标记值为 1200，现金为 8900，权益 10100，盈亏为 100。
    assert Decimal(position["unrealized_pnl"]) == Decimal("100")
    account = alice_client.account()
    assert account.status_code == 200
    assert Decimal(account.json()["equity"]) == Decimal("10100")

    partial_close = alice_client.place_order(ATM_CALL, "sell", "6000", DEFAULT_QUANTITY)
    assert partial_close.status_code == 200
    assert partial_close.json()["status"] == "filled"
    position_response = alice_client.positions()
    assert position_response.status_code == 200
    position = position_response.json()[0]
    assert Decimal(position["quantity"]) == Decimal("0.1")
    assert Decimal(position["average_price"]) == Decimal("5500")
    # 剩余 0.1 张多仓仍按 5500 均价，(6000-5500)*0.1=50。
    assert Decimal(position["unrealized_pnl"]) == Decimal("50")

    reverse_order = alice_client.place_order(ATM_CALL, "sell", "6000", "0.2")
    assert reverse_order.status_code == 200
    assert reverse_order.json()["status"] == "filled"
    position_response = alice_client.positions()
    assert position_response.status_code == 200
    position = position_response.json()[0]
    assert Decimal(position["quantity"]) == Decimal("-0.1")
    assert Decimal(position["average_price"]) == Decimal("6000")
    # 净仓翻为空头后按本次成交价建仓，故当前未实现盈亏为 0。
    assert Decimal(position["unrealized_pnl"]) == Decimal("0")
    account = alice_client.account()
    assert account.status_code == 200
    assert Decimal(account.json()["balance"]) == Decimal("10700")
    assert Decimal(account.json()["equity"]) == Decimal("10100")


def test_index_change_recalculates_margin(alice_client):
    short_order = alice_client.place_order(OTM_CALL, "sell", "2000", DEFAULT_QUANTITY)
    assert short_order.status_code == 200
    assert short_order.json()["status"] == "filled"
    before = alice_client.account()
    assert before.status_code == 200
    # 指数 100000 时虚值额 10000，保证金 max(15000-10000,10000)+2000，再乘 0.1=1200。
    assert Decimal(before.json()["balance"]) == Decimal("10200")
    assert Decimal(before.json()["available"]) == Decimal("9000")
    assert Decimal(before.json()["maintenance_margin"]) == Decimal("950")

    mark_update = alice_client.set_mark_price(OTM_CALL, "2000", index_price="110000")
    assert mark_update.status_code == 200
    assert Decimal(mark_update.json()["index_price"]) == Decimal("110000")
    after = alice_client.account()
    assert after.status_code == 200
    # 指数 110000 时该看涨期权为平值，保证金 (16500+2000)*0.1=1850，可用额 8350。
    assert Decimal(after.json()["balance"]) == Decimal("10200")
    assert Decimal(after.json()["available"]) == Decimal("8350")
    assert Decimal(after.json()["maintenance_margin"]) == Decimal("1025")
    assert after.json()["status"] == "active"



def test_negative_available_without_liquidation(alice_client):
    second_short = alice_client.place_order(ATM_CALL, "sell", CALL_MARK_PRICE, "0.4")
    assert second_short.status_code == 200
    assert second_short.json()["status"] == "filled"
    mark_update = alice_client.set_mark_price(ATM_CALL, CALL_MARK_PRICE, index_price="200000")
    assert mark_update.status_code == 200
    margin_call = alice_client.account()
    assert margin_call.status_code == 200
    # 余额 12000，空仓市值 -2000，权益 10000；初始保证金 14000，可用额 -2000。
    # 维持保证金为 8000，权益仍高于维持线，因此只形成保证金不足状态，不清算。
    assert Decimal(margin_call.json()["balance"]) == Decimal("12000")
    assert Decimal(margin_call.json()["available"]) == Decimal("-2000")
    assert Decimal(margin_call.json()["equity"]) == Decimal("10000")
    assert Decimal(margin_call.json()["maintenance_margin"]) == Decimal("8000")
    assert margin_call.json()["status"] == "active"
    liquidations = alice_client.liquidations()
    assert liquidations.status_code == 200
    assert liquidations.json() == []


def test_liquidation_strict_maintenance_boundary(alice_client):
    short_order = alice_client.place_order(ATM_CALL, "sell", CALL_MARK_PRICE, DEFAULT_QUANTITY)
    assert short_order.status_code == 200
    assert short_order.json()["status"] == "filled"

    equal_mark = alice_client.set_mark_price(ATM_CALL, "48750")
    assert equal_mark.status_code == 200
    equal_account = alice_client.account()
    assert equal_account.status_code == 200
    # 权益 10500-4875=5625，维持额 (7500+48750)*0.1=5625，等于时不清算。
    assert Decimal(equal_account.json()["equity"]) == Decimal("5625")
    assert Decimal(equal_account.json()["maintenance_margin"]) == Decimal("5625")
    assert equal_account.json()["status"] == "active"

    above_mark = alice_client.set_mark_price(ATM_CALL, "48750.5")
    assert above_mark.status_code == 200
    above_account = alice_client.account()
    assert above_account.status_code == 200
    # 上涨 0.5 后，权益 5624.95，小于维持额 5625.05，清算余额为权益。
    assert Decimal(above_account.json()["equity"]) == Decimal("5624.95")
    assert Decimal(above_account.json()["maintenance_margin"]) == Decimal("0")
    records = alice_client.liquidations()
    assert records.status_code == 200
    assert Decimal(records.json()[0]["equity_before"]) == Decimal("5624.95")
    assert Decimal(records.json()[0]["maintenance_margin"]) == Decimal("5625.05")
    assert above_account.json()["status"] == "liquidated"
    assert Decimal(above_account.json()["balance"]) == Decimal("5624.95")
