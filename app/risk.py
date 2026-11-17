from datetime import datetime, timezone
from . import store
from .config import ZERO
from .trading import account, instrument_named, number, positions
from .auth import fail


def ticker(name):
    return dict(instrument=name, mark_price=store.instruments[name]["mark_price"], index_price=store.index_price)


def update_price(name, mark_price, index_price=None):
    """调用方持锁，改价和清算使用同一份状态。"""
    instrument = instrument_named(name)
    mark = number(mark_price, "mark_price")
    index = number(index_price, "index_price") if index_price is not None else store.index_price
    if mark < ZERO:
        fail(400, "INVALID_PARAM", "标记价格不能为负数", "mark_price")
    if index <= ZERO:
        fail(400, "INVALID_PARAM", "指数价格必须为正数", "index_price")
    instrument["mark_price"] = mark
    store.index_price = index
    for username, user in store.users.items():
        summary = account(username)
        if any(position["quantity"] < ZERO for position in user["positions"].values()) and summary["equity"] < summary["maintenance_margin"]:
            closed = positions(username)
            for order in store.orders.values():
                if order["username"] == username and order["status"] == "open":
                    order["status"] = "cancelled"
            # 平仓收付持仓市值；负权益归零，另记缺口。
            user["balance"] = max(summary["equity"], ZERO)
            user["positions"].clear()
            user["status"] = "liquidated"
            user["liquidations"].append(dict(time=datetime.now(timezone.utc).isoformat(),
                equity_before=summary["equity"], maintenance_margin=summary["maintenance_margin"],
                positions_closed=closed, shortfall=max(-summary["equity"], ZERO)))
    return ticker(name)
