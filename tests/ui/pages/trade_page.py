from playwright.sync_api import expect
from .base_page import BasePage, UI_TIMEOUT_MILLISECONDS


class TradePage(BasePage):
    def __init__(self, page, base_url):
        super().__init__(page, base_url)
        self.balance = page.get_by_test_id("account-balance")
        self.available = page.get_by_test_id("account-available")
        self.frozen = page.get_by_test_id("account-frozen")
        self.status = page.get_by_test_id("account-status")
        self.instrument = page.get_by_test_id("instrument-select")
        self.side = page.get_by_test_id("order-side-select")
        self.price = page.get_by_test_id("order-price-input")
        self.quantity = page.get_by_test_id("order-quantity-input")
        self.submit_button = page.get_by_test_id("submit-order-button")
        self.refresh_button = page.get_by_test_id("refresh-data-button")
        self.open_order_rows = page.get_by_test_id("open-order-row")
        self.position_rows = page.get_by_test_id("position-row")
        self.position_quantity = page.get_by_test_id("position-quantity")
        self.order_message = page.get_by_test_id("order-message")
        self.trade_message = page.get_by_test_id("trade-message")
        self.cancel_buttons = page.get_by_test_id("cancel-order-button")

    def wait_until_ready(self):
        self.page.wait_for_url(self.base_url + "/trade")
        expect(self.status).to_have_text("active", timeout=UI_TIMEOUT_MILLISECONDS)
        expect(self.refresh_button).to_be_enabled(timeout=UI_TIMEOUT_MILLISECONDS)

    def place_order(self, instrument, side, price, quantity):
        # 避免初次加载或刷新重建下拉选项时覆盖填写内容。
        expect(self.refresh_button).to_be_enabled(timeout=UI_TIMEOUT_MILLISECONDS)
        self.instrument.select_option(instrument)
        self.side.select_option(side)
        self.price.fill(price)
        self.quantity.fill(quantity)
        self.submit_button.click()
        expect(self.submit_button).to_be_enabled(timeout=UI_TIMEOUT_MILLISECONDS)

    def cancel_first_open_order(self):
        self.cancel_buttons.first.click()

    def read_account_summary(self):
        return dict(balance=self.balance.inner_text().strip(),
                    available=self.available.inner_text().strip(),
                    frozen=self.frozen.inner_text().strip(), status=self.status.inner_text().strip())
