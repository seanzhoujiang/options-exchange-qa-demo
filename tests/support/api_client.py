import requests
from .test_data import HTTP_TIMEOUT_SECONDS


class ApiClient:
    def __init__(self, base_url, token=None):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def close(self):
        self.session.close()

    def _request(self, method, path, **kwargs):
        return self.session.request(method, self.base_url + path, timeout=HTTP_TIMEOUT_SECONDS, **kwargs)

    def get_captcha(self):
        return self._request("POST", "/api/auth/captcha")

    def login(self, username, password, captcha_id, captcha_code):
        return self._request("POST", "/api/auth/login", json=dict(username=username, password=password, captcha_id=captcha_id, captcha_code=captcha_code))

    def logout(self):
        return self._request("POST", "/api/auth/logout")

    def change_password(self, old_password, new_password, captcha_id, captcha_code):
        return self._request("POST", "/api/auth/change-password", json=dict(old_password=old_password, new_password=new_password, captcha_id=captcha_id, captcha_code=captcha_code))

    def account(self):
        return self._request("GET", "/api/account")

    def instruments(self):
        return self._request("GET", "/api/instruments")

    def ticker(self, instrument):
        return self._request("GET", f"/api/market/ticker/{instrument}")

    def place_order(self, instrument, side, price, quantity):
        return self._request("POST", "/api/orders", json=dict(instrument=instrument, side=side, price=price, quantity=quantity))

    def cancel_order(self, order_id):
        return self._request("DELETE", f"/api/orders/{order_id}")

    def get_order(self, order_id):
        return self._request("GET", f"/api/orders/{order_id}")

    def list_orders(self, status=None):
        return self._request("GET", "/api/orders", params={} if status is None else dict(status=status))

    def positions(self):
        return self._request("GET", "/api/positions")

    def liquidations(self):
        return self._request("GET", "/api/liquidations")

    def set_mark_price(self, instrument, mark_price, index_price=None):
        payload = dict(instrument=instrument, mark_price=mark_price)
        if index_price is not None:
            payload["index_price"] = index_price
        return self._request("POST", "/api/test/mark-price", json=payload)

    def reset(self):
        return self._request("POST", "/api/test/reset")
