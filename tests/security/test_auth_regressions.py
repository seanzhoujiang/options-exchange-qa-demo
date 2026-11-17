import json
import pytest
from tests.support.test_data import CHANGED_PASSWORD, HTTP_TIMEOUT_SECONDS, SEED_USERS

pytestmark = pytest.mark.security
LONE_SURROGATE = chr(0xD800)


def _post_json(client, path, payload):
    return client.session.post(
        client.base_url + path,
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )


def _new_captcha(api_client):
    result = api_client.get_captcha()
    assert result.status_code == 200
    return result.json()


@pytest.mark.parametrize(
    "endpoint,field",
    [
        ("login", "password"),
        ("login", "captcha_code"),
        ("change-password", "old_password"),
        ("change-password", "new_password"),
        ("change-password", "captcha_code"),
    ],
)
def test_surrogate_auth_fields_rejected(
    endpoint, field, alice_client, api_client
):
    captcha = _new_captcha(api_client)
    if endpoint == "login":
        payload = dict(username="alice", password=SEED_USERS["alice"], **captcha)
        client = api_client
        path = "/api/auth/login"
    else:
        payload = dict(
            old_password=SEED_USERS["alice"],
            new_password=CHANGED_PASSWORD,
            **captcha,
        )
        client = alice_client
        path = "/api/auth/change-password"
    payload[field] = LONE_SURROGATE
    result = _post_json(client, path, payload)
    assert result.status_code == 400
    assert result.json()["code"] == "INVALID_PARAM"
    assert result.json()["field"] == field


def test_password_change_revokes_all_existing_user_tokens(login_as, api_client):
    first_client = login_as("alice")
    second_client = login_as("alice")
    captcha = _new_captcha(api_client)
    result = first_client.change_password(
        SEED_USERS["alice"], CHANGED_PASSWORD, **captcha
    )
    assert result.status_code == 200
    assert result.json()["message"] == "密码已修改"
    for client in (first_client, second_client):
        account = client.account()
        assert account.status_code == 401
        assert account.json()["code"] == "UNAUTHORIZED"


def test_logout_revokes_current_token(alice_client):
    result = alice_client.logout()
    assert result.status_code == 200
    account = alice_client.account()
    assert account.status_code == 401
    assert account.json()["code"] == "UNAUTHORIZED"


def test_reset_invalidates_existing_token(alice_client):
    result = alice_client.reset()
    assert result.status_code == 200
    assert result.json()["message"] == "状态已重置"
    account = alice_client.account()
    assert account.status_code == 401
    assert account.json()["code"] == "UNAUTHORIZED"
