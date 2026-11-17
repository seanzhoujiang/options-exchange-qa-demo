import json
from urllib.parse import urlsplit, urlunsplit
from decimal import Decimal
import pytest
from websockets.sync.client import connect
from tests.support.test_data import ATM_CALL, INSTRUMENT_NAMES

pytestmark = pytest.mark.api
WEBSOCKET_RECEIVE_TIMEOUT_SECONDS = 5
UPDATED_MARK_PRICE = "6000"


def test_ticker_websocket_sends_snapshot_and_mark_update(api_client):
    address = urlsplit(api_client.base_url)
    websocket_scheme = "wss" if address.scheme == "https" else "ws"
    websocket_url = urlunsplit((websocket_scheme, address.netloc, "/ws/ticker", "", ""))
    with connect(websocket_url, open_timeout=WEBSOCKET_RECEIVE_TIMEOUT_SECONDS) as websocket:
        snapshot = json.loads(websocket.recv(timeout=WEBSOCKET_RECEIVE_TIMEOUT_SECONDS))
        assert isinstance(snapshot, list)
        assert len(snapshot) == 4
        assert {ticker["instrument"] for ticker in snapshot} == set(INSTRUMENT_NAMES)
        initial_ticker = next(ticker for ticker in snapshot if ticker["instrument"] == ATM_CALL)
        assert Decimal(initial_ticker["mark_price"]) == Decimal("5000")

        changed = api_client.set_mark_price(ATM_CALL, UPDATED_MARK_PRICE)
        assert changed.status_code == 200
        assert changed.json()["instrument"] == ATM_CALL
        assert Decimal(changed.json()["mark_price"]) == Decimal(UPDATED_MARK_PRICE)
        update = json.loads(websocket.recv(timeout=WEBSOCKET_RECEIVE_TIMEOUT_SECONDS))
        assert update["instrument"] == ATM_CALL
        assert Decimal(update["mark_price"]) == Decimal(UPDATED_MARK_PRICE)
        assert Decimal(update["index_price"]) == Decimal("100000")
