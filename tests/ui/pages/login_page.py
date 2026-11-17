import re
from playwright.sync_api import expect
from tests.support.test_data import CAPTCHA_DIGITS
from .base_page import BasePage, UI_TIMEOUT_MILLISECONDS


class LoginPage(BasePage):
    def __init__(self, page, base_url):
        super().__init__(page, base_url)
        self.username = page.get_by_test_id("username-input")
        self.password = page.get_by_test_id("password-input")
        self.captcha_input = page.get_by_test_id("captcha-input")
        self.captcha_code = page.get_by_test_id("captcha-code")
        self.captcha_button = page.get_by_test_id("refresh-captcha-button")
        self.submit_button = page.get_by_test_id("login-submit-button")
        self.message = page.get_by_test_id("login-message")

    def open(self):
        self.open_path("/login")
        self.read_captcha_code()

    def read_captcha_code(self):
        expect(self.captcha_code).to_have_text(
            re.compile(rf"^[0-9]{{{CAPTCHA_DIGITS}}}$"), timeout=UI_TIMEOUT_MILLISECONDS,
        )
        expect(self.captcha_button).to_be_enabled(timeout=UI_TIMEOUT_MILLISECONDS)
        return self.captcha_code.inner_text().strip()

    def login_as(self, username, password, captcha_code=None):
        code = self.read_captcha_code() if captcha_code is None else captcha_code
        self.username.fill(username)
        self.password.fill(password)
        self.captcha_input.fill(code)
        self.submit_button.click()
