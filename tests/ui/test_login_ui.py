import re
from decimal import Decimal

import pytest
from playwright.sync_api import expect

from tests.support.test_data import CAPTCHA_DIGITS, SEED_USERS
from tests.ui.pages.trade_page import TradePage


pytestmark = pytest.mark.ui


def test_login_opens_trade_page_with_seed_account(login_page, base_url):
    login_page.login_as("alice", SEED_USERS["alice"])

    trade_page = TradePage(login_page.page, base_url)
    trade_page.wait_until_ready()

    expect(trade_page.balance).to_have_text(re.compile(r"^\s*10000(?:\.0+)?\s*$"))
    summary = trade_page.read_account_summary()
    assert Decimal(summary["balance"]) == Decimal("10000")
    assert Decimal(summary["available"]) == Decimal("10000")
    assert Decimal(summary["frozen"]) == Decimal("0")
    expect(trade_page.status).to_have_text("active")


def test_invalid_captcha_stays_on_login_page(login_page):
    displayed_captcha = login_page.read_captcha_code()
    zero_code = "0" * CAPTCHA_DIGITS
    invalid_captcha = (
        zero_code
        if displayed_captcha != zero_code
        else "1" + "0" * (CAPTCHA_DIGITS - 1)
    )

    login_page.login_as(
        "alice", SEED_USERS["alice"], captcha_code=invalid_captcha
    )

    expect(login_page.page).to_have_url(re.compile(r".*/login/?$"))
    expect(login_page.message).to_have_text("验证码无效、已过期或已使用")
