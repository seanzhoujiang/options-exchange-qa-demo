from decimal import Decimal
from uuid import uuid4
from . import store
from .auth import fail
from .config import (
    DECIMAL_MAX_DIGITS, MAINTENANCE_MARGIN_RATE, MAX_PRICE, MAX_QUANTITY,
    MIN_QUANTITY, MIN_SHORT_MARGIN_RATE, PLAIN_DECIMAL_PATTERN, PRICE_TICK, QUANTITY_STEP,
    SHORT_MARGIN_RATE, ZERO,
)


def number(value, field):
    text = str(value)
    if PLAIN_DECIMAL_PATTERN.fullmatch(text) is None:
        fail(400, "INVALID_PARAM", "必须为普通十进制数，不能含指数或下划线", field)
    parsed = Decimal(text)
    if len(parsed.as_tuple().digits) > DECIMAL_MAX_DIGITS or abs(parsed.adjusted()) > DECIMAL_MAX_DIGITS:
        fail(400, "INVALID_PARAM", "必须为普通十进制数，不能含指数或下划线", field)
    return parsed


def instrument_named(name):
    if name not in store.instruments:
        fail(404, "INSTRUMENT_NOT_FOUND", "合约不存在", "instrument")
    return store.instruments[name]


def unrealized(position, instrument):
    return (instrument["mark_price"] - position["average_price"]) * position["quantity"]


def short_margin(instrument, price, quantity):
    strike = instrument["strike"]
    out_of_money = max(strike - store.index_price if instrument["option_type"] == "call"
                       else store.index_price - strike, ZERO)
    return (max(SHORT_MARGIN_RATE * store.index_price - out_of_money,
                MIN_SHORT_MARGIN_RATE * store.index_price) + price) * quantity


def account(username):
    user = store.users[username]
    frozen = sum((order["required"] for order in store.orders.values()
                  if order["username"] == username and order["status"] == "open"), ZERO)
    position_margin = ZERO
    position_value = ZERO
    maintenance = ZERO
    for name, position in user["positions"].items():
        instrument = store.instruments[name]
        # 权利金已收付，权益计入持仓市值，盈亏仅用于展示。
        position_value += instrument["mark_price"] * position["quantity"]
        if position["quantity"] < ZERO:
            quantity = abs(position["quantity"])
            position_margin += short_margin(instrument, instrument["mark_price"], quantity)
            maintenance += (MAINTENANCE_MARGIN_RATE * store.index_price + instrument["mark_price"]) * quantity
    return dict(username=username, balance=user["balance"], available=user["balance"] - frozen - position_margin,
                frozen=frozen, equity=user["balance"] + position_value, maintenance_margin=maintenance, status=user["status"])


def fill(order):
    user = store.users[order["username"]]
    premium = store.instruments[order["instrument"]]["mark_price"]
    signed_quantity = order["quantity"] if order["side"] == "buy" else -order["quantity"]
    # 权利金在这里收付，反向净仓不再额外结算盈亏。
    user["balance"] -= premium * signed_quantity
    previous = user["positions"].get(order["instrument"])
    average_price = premium
    net_quantity = signed_quantity
    if previous:
        old_quantity = previous["quantity"]
        net_quantity += old_quantity
        if old_quantity * signed_quantity > ZERO:
            average_price = (previous["average_price"] * abs(old_quantity) + premium * abs(signed_quantity)) / abs(net_quantity)
        elif abs(old_quantity) > abs(signed_quantity):
            average_price = previous["average_price"]
    if net_quantity == ZERO:
        user["positions"].pop(order["instrument"])
    else:
        user["positions"][order["instrument"]] = dict(quantity=net_quantity, average_price=average_price)
    order.update(status="filled", fill_price=premium)


def place(username, instrument, side, price, quantity):
    contract = instrument_named(instrument)
    if side not in ("buy", "sell"):
        fail(400, "INVALID_PARAM", "方向必须为买入或卖出", "side")
    price = number(price, "price")
    quantity = number(quantity, "quantity")
    if price <= ZERO or price > MAX_PRICE or price % PRICE_TICK:
        fail(400, "INVALID_PARAM", "价格超出范围或不符合最小价位", "price")
    if quantity < MIN_QUANTITY or quantity > MAX_QUANTITY or quantity % QUANTITY_STEP:
        fail(400, "INVALID_PARAM", "数量超出范围或不符合步长", "quantity")
    if store.users[username]["status"] != "active":
        fail(403, "ACCOUNT_LIQUIDATED", "账户已清算")
    # 平多部分不计空头保证金。
    position = store.users[username]["positions"].get(instrument)
    long_quantity = max(position["quantity"], ZERO) if position else ZERO
    short_quantity = max(quantity - long_quantity, ZERO)
    required = price * quantity if side == "buy" else short_margin(contract, price, short_quantity)
    if required > ZERO and required > account(username)["available"]:
        fail(400, "INSUFFICIENT_MARGIN", "可用保证金不足")
    order = dict(order_id=uuid4().hex, username=username, instrument=instrument, side=side,
                 price=price, quantity=quantity, required=required, status="open")
    store.orders[order["order_id"]] = order
    if (side == "buy" and price >= contract["mark_price"]) or (side == "sell" and price <= contract["mark_price"]):
        fill(order)
    return order


def owned_order(username, order_id):
    order = store.orders.get(order_id)
    if order is None or order["username"] != username:
        fail(404, "ORDER_NOT_FOUND", "订单不存在")
    return order


def cancel(username, order_id):
    order = owned_order(username, order_id)
    if order["status"] != "open":
        fail(409, "ORDER_NOT_CANCELLABLE", "订单不可撤销")
    order["status"] = "cancelled"
    return order


def positions(username):
    return [dict(instrument=name, **position, mark_price=store.instruments[name]["mark_price"],
                 unrealized_pnl=unrealized(position, store.instruments[name]))
            for name, position in store.users[username]["positions"].items()]
