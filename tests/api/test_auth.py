import pytest
from tests.support.test_data import (
    CAPTCHA_DIGITS, CHANGED_PASSWORD, INVALID_TOKEN, SEED_USERS, UNKNOWN_USERNAME, WRONG_PASSWORD,
)

pytestmark = pytest.mark.api


def test_login_success(api_client):
    captcha = api_client.get_captcha()
    assert captcha.status_code == 200
    assert len(captcha.json()["captcha_code"]) == CAPTCHA_DIGITS
    assert captcha.json()["captcha_code"].isdigit()
    result = api_client.login("alice", SEED_USERS["alice"], **captcha.json())
    assert result.status_code == 200
    assert isinstance(result.json()["token"], str) and result.json()["token"]


def test_bad_credentials_have_identical_response_bodies(api_client):
    bodies = []
    for username in ("alice", UNKNOWN_USERNAME):
        captcha = api_client.get_captcha()
        assert captcha.status_code == 200
        result = api_client.login(username, WRONG_PASSWORD, **captcha.json())
        assert result.status_code == 401
        assert result.json()["code"] == "BAD_CREDENTIALS"
        bodies.append(result.json())
    assert bodies[0] == bodies[1]


def test_wrong_captcha_is_consumed(api_client):
    captcha = api_client.get_captcha()
    assert captcha.status_code == 200
    payload = captcha.json()
    wrong_code = "111111" if payload["captcha_code"] != "111111" else "222222"
    result = api_client.login("alice", SEED_USERS["alice"], payload["captcha_id"], wrong_code)
    assert result.status_code == 400
    assert result.json()["code"] == "CAPTCHA_INVALID"
    retry = api_client.login("alice", SEED_USERS["alice"], **payload)
    assert retry.status_code == 400
    assert retry.json()["code"] == "CAPTCHA_INVALID"


def test_captcha_cannot_be_reused(api_client):
    captcha = api_client.get_captcha()
    assert captcha.status_code == 200
    result = api_client.login("alice", SEED_USERS["alice"], **captcha.json())
    assert result.status_code == 200
    assert result.json()["token"]
    reused = api_client.login("alice", SEED_USERS["alice"], **captcha.json())
    assert reused.status_code == 400
    assert reused.json()["code"] == "CAPTCHA_INVALID"


@pytest.mark.parametrize("token", [None, INVALID_TOKEN], ids=["missing", "invalid"])
def test_account_requires_valid_token(api_client, token):
    if token:
        api_client.session.headers["Authorization"] = f"Bearer {token}"
    result = api_client.account()
    assert result.status_code == 401
    assert result.json()["code"] == "UNAUTHORIZED"


def test_change_password_replaces_old_password(alice_client, api_client):
    captcha = api_client.get_captcha()
    assert captcha.status_code == 200
    result = alice_client.change_password(SEED_USERS["alice"], CHANGED_PASSWORD, **captcha.json())
    assert result.status_code == 200
    assert result.json()["message"] == "密码已修改"
    for password, expected_status in ((SEED_USERS["alice"], 401), (CHANGED_PASSWORD, 200)):
        captcha = api_client.get_captcha()
        assert captcha.status_code == 200
        login = api_client.login("alice", password, **captcha.json())
        assert login.status_code == expected_status
        if expected_status == 401:
            assert login.json()["code"] == "BAD_CREDENTIALS"
        else:
            assert login.json()["token"]


@pytest.mark.parametrize(
    "old_password,new_password,expected_status",
    [
        ("wrong-old-pass", "new-valid-password", 401),
        (SEED_USERS["alice"], "short7!", 400),
        (SEED_USERS["alice"], "x" * 65, 400),
        (SEED_USERS["alice"], "12345678", 200),
        (SEED_USERS["alice"], "x" * 64, 200),
    ],
    ids=["wrong-old-password", "new-password-seven", "new-password-sixty-five",
         "new-password-eight", "new-password-sixty-four"],
)
def test_change_password_boundaries(
    alice_client, api_client, old_password, new_password, expected_status
):
    captcha = api_client.get_captcha()
    assert captcha.status_code == 200
    result = alice_client.change_password(old_password, new_password, **captcha.json())
    assert result.status_code == expected_status
    if expected_status in (400, 401):
        expected_code = "BAD_CREDENTIALS" if expected_status == 401 else "INVALID_PARAM"
        assert result.json()["code"] == expected_code
        old_login_captcha = api_client.get_captcha()
        assert old_login_captcha.status_code == 200
        old_login = api_client.login("alice", SEED_USERS["alice"], **old_login_captcha.json())
        assert old_login.status_code == 200
        assert old_login.json()["token"]
    else:
        assert result.json()["message"] == "密码已修改"
        old_token_result = alice_client.account()
        assert old_token_result.status_code == 401
        assert old_token_result.json()["code"] == "UNAUTHORIZED"
