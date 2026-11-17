import re
from decimal import Decimal

import pytest
from playwright.sync_api import expect

from tests.support.test_data import (
    ATM_CALL,
    CALL_MARK_PRICE,
    DEFAULT_QUANTITY,
    RESTING_BUY_PRICE,
)


pytestmark = pytest.mark.ui


def _expect_decimal_text(locator, expected_literal):
    expected_value = Decimal(expected_literal)
    canonical_value = format(expected_value, "f")
    integer_part, separator, fractional_part = canonical_value.partition(".")
    if separator:
        significant_fraction = fractional_part.rstrip("0")
        decimal_pattern = (
            re.escape(integer_part)
            + r"\."
            + re.escape(significant_fraction)
            + r"0*"
        )
    else:
        decimal_pattern = re.escape(integer_part) + r"(?:\.0+)?"

    expect(locator).to_have_text(re.compile(r"^\s*" + decimal_pattern + r"\s*$"))
    actual_snapshot = locator.inner_text().strip()
    assert Decimal(actual_snapshot) == expected_value


def test_resting_buy_shows_order_and_freezes_ten(trade_page):
    trade_page.place_order(
        ATM_CALL, "buy", RESTING_BUY_PRICE, DEFAULT_QUANTITY
    )

    expect(trade_page.open_order_rows).to_have_count(1)
    expect(trade_page.open_order_rows).to_contain_text(ATM_CALL)
    expect(trade_page.open_order_rows).to_contain_text("open")
    _expect_decimal_text(trade_page.frozen, "10")


def test_cancel_resting_buy_releases_frozen_amount_and_removes_row(trade_page):
    trade_page.place_order(
        ATM_CALL, "buy", RESTING_BUY_PRICE, DEFAULT_QUANTITY
    )
    expect(trade_page.open_order_rows).to_have_count(1)
    expect(trade_page.open_order_rows).to_contain_text(ATM_CALL)
    expect(trade_page.open_order_rows).to_contain_text("open")
    _expect_decimal_text(trade_page.frozen, "10")

    trade_page.cancel_first_open_order()

    expect(trade_page.trade_message).to_have_text("委托已撤销。")
    _expect_decimal_text(trade_page.frozen, "0")
    expect(trade_page.open_order_rows).to_have_count(0)


def test_filled_sell_shows_short_position(trade_page):
    trade_page.place_order(
        ATM_CALL, "sell", CALL_MARK_PRICE, DEFAULT_QUANTITY
    )

    expect(trade_page.position_rows).to_have_count(1)
    expect(trade_page.position_rows).to_contain_text(ATM_CALL)
    expect(trade_page.open_order_rows).to_have_count(0)
    _expect_decimal_text(trade_page.balance, "10500")
    _expect_decimal_text(trade_page.position_quantity, "-0.1")
