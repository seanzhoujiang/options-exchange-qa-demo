from playwright.sync_api import Page

UI_TIMEOUT_MILLISECONDS = 10_000


class BasePage:
    def __init__(self, page: Page, base_url: str):
        self.page = page
        self.base_url = base_url.rstrip("/")
        self.page.set_default_timeout(UI_TIMEOUT_MILLISECONDS)

    def open_path(self, path: str):
        self.page.goto(self.base_url + path)
