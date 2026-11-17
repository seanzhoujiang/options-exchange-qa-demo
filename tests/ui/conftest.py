import os

# 浏览器装在虚拟环境内，CI 也使用这个路径。
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

import pytest
from tests.support.test_data import SEED_USERS
from tests.ui.pages.login_page import LoginPage
from tests.ui.pages.trade_page import TradePage


@pytest.fixture
def login_page(page, base_url, reset_state):
    login = LoginPage(page, base_url)
    login.open()
    return login


@pytest.fixture
def trade_page(login_page, base_url):
    login_page.login_as("alice", SEED_USERS["alice"])
    trade = TradePage(login_page.page, base_url)
    trade.wait_until_ready()
    return trade
