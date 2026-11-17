from decimal import Decimal
import json
import pytest
from tests.support.test_data import ATM_CALL, DEFAULT_QUANTITY, HTTP_TIMEOUT_SECONDS, RESTING_BUY_PRICE

pytestmark = pytest.mark.security
LONG_INSTRUMENT_LENGTH = 10_000


def _post_order(client, payload):
    return client.session.post(client.base_url + "/api/orders", data=json.dumps(payload),
                               headers={"Content-Type": "application/json"}, timeout=HTTP_TIMEOUT_SECONDS)


def _resting_payload():
    return dict(instrument=ATM_CALL, side="buy", price=RESTING_BUY_PRICE, quantity=DEFAULT_QUANTITY)


@pytest.mark.parametrize("extra_field,extra_value", [("username", "bob"), ("status", "filled"), ("required", "0")])
def test_extra_fields_cannot_override_server_order_values(alice_client, bob_client, extra_field, extra_value):
    before_account = alice_client.account()
    assert before_account.status_code == 200
    frozen_before = Decimal(before_account.json()["frozen"])
    assert frozen_before == Decimal("0")
    before_orders = alice_client.list_orders()
    assert before_orders.status_code == 200
    assert before_orders.json() == []

    payload = _resting_payload()
    payload[extra_field] = extra_value
    # 服务端通过严格模式拒绝未知字段，这是忽略与拒绝两种安全选项中更严格的一种。
    result = _post_order(alice_client, payload)
    assert result.status_code == 400
    assert result.json()["code"] == "INVALID_PARAM"
    assert result.json()["field"] == extra_field

    alice_orders = alice_client.list_orders()
    assert alice_orders.status_code == 200
    assert alice_orders.json() == []
    bob_orders = bob_client.list_orders()
    assert bob_orders.status_code == 200
    assert bob_orders.json() == []
    after_account = alice_client.account()
    assert after_account.status_code == 200
    assert Decimal(after_account.json()["frozen"]) == frozen_before


@pytest.mark.parametrize("field", ["price", "quantity"])
@pytest.mark.parametrize("value", ["-0.5", "0", "1e1000", "NaN", "Infinity", "-Infinity", -1, 0, "1e2", "1_00"])
def test_hostile_numbers_do_not_freeze_funds(alice_client, field, value):
    payload = _resting_payload()
    payload[field] = value
    result = _post_order(alice_client, payload)
    assert result.status_code == 400
    assert result.json()["code"] == "INVALID_PARAM"
    assert result.json()["field"] == field
    expected_frozen = Decimal("0")
    account = alice_client.account()
    assert account.status_code == 200
    assert Decimal(account.json()["frozen"]) == expected_frozen
    assert Decimal(account.json()["frozen"]) >= Decimal("0")
    assert Decimal(account.json()["balance"]) == Decimal("10000")


@pytest.mark.parametrize("field", ["price", "quantity"])
@pytest.mark.parametrize("kind", ["decimal-string", "json-number", "invalid-string", "object", "boolean"])
def test_order_types_are_validated_on_server(alice_client, field, kind):
    payload = _resting_payload()
    if kind == "json-number":
        payload[field] = 100 if field == "price" else 0.1
    elif kind == "invalid-string":
        payload[field] = "not-a-number"
    elif kind == "object":
        payload[field] = {"value": "100"}
    elif kind == "boolean":
        payload[field] = True
    result = _post_order(alice_client, payload)
    accepted = kind in ("decimal-string", "json-number")
    assert result.status_code == (200 if accepted else 400)
    if accepted:
        assert result.json()["status"] == "open"
        assert Decimal(result.json()["required"]) == Decimal("10")
    else:
        assert result.json()["code"] == "INVALID_PARAM"
        if kind == "invalid-string":
            assert result.json()["field"] == field
    account = alice_client.account()
    assert account.status_code == 200
    assert Decimal(account.json()["frozen"]) == Decimal("10" if accepted else "0")


def test_very_long_instrument_is_rejected_without_server_error(alice_client):
    payload = _resting_payload()
    payload["instrument"] = "X" * LONG_INSTRUMENT_LENGTH
    result = _post_order(alice_client, payload)
    assert result.status_code == 404
    assert result.json()["code"] == "INSTRUMENT_NOT_FOUND"
    assert result.json()["field"] == "instrument"


@pytest.mark.parametrize("body", [[], ["order"], "order", 100, None])
def test_non_object_order_body_is_rejected(alice_client, body):
    result = _post_order(alice_client, body)
    assert result.status_code == 400
    assert result.json()["code"] == "INVALID_PARAM"


@pytest.mark.parametrize("field", ["price", "quantity"])
def test_numeric_exponents_in_json_body_are_rejected(alice_client, field):
    payload = _resting_payload()
    payload[field] = "1e2"
    body = json.dumps(payload).replace('"1e2"', '1e2')
    result = alice_client.session.post(alice_client.base_url + "/api/orders", data=body,
                                       headers={"Content-Type": "application/json"}, timeout=HTTP_TIMEOUT_SECONDS)
    assert result.status_code == 400
    assert result.json()["code"] == "INVALID_PARAM"
    assert result.json()["field"] == field
