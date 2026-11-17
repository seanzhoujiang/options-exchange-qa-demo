import pytest
from tests.support.test_data import CAPTCHA_DIGITS, CHANGED_PASSWORD, HTTP_TIMEOUT_SECONDS, SEED_USERS

pytestmark = pytest.mark.security
CAPTCHA_PAIR_ATTEMPTS = 10
CAPTCHA_ATTACKS = ("missing", "empty", "mismatched", "wrong_then_correct")


def _captcha(client):
    result = client.get_captcha()
    assert result.status_code == 200
    return result.json()


def _attack_payloads(client, attack):
    if attack == "missing":
        return [{}]
    original = _captcha(client)
    if attack == "empty":
        return [dict(captcha_id=original["captcha_id"], captcha_code="")]
    if attack == "mismatched":
        # 两个有效请求交叉配对；避免六位随机验证码偶然相同导致误报。
        for _ in range(CAPTCHA_PAIR_ATTEMPTS):
            other = _captcha(client)
            if other["captcha_code"] != original["captcha_code"]:
                return [dict(captcha_id=other["captcha_id"], captcha_code=original["captcha_code"])]
        pytest.fail("多次生成的验证码均相同，无法建立交叉配对前置条件")
    wrong_code = "0" * CAPTCHA_DIGITS
    if wrong_code == original["captcha_code"]:
        wrong_code = "1" * CAPTCHA_DIGITS
    return [dict(captcha_id=original["captcha_id"], captcha_code=wrong_code), original]


@pytest.mark.parametrize("attack", CAPTCHA_ATTACKS)
def test_login_requires_server_side_captcha(api_client, attack):
    for captcha_fields in _attack_payloads(api_client, attack):
        payload = dict(username="alice", password=SEED_USERS["alice"], **captcha_fields)
        result = api_client.session.post(api_client.base_url + "/api/auth/login", json=payload, timeout=HTTP_TIMEOUT_SECONDS)
        assert result.status_code == 400
        assert result.json()["code"] == ("INVALID_PARAM" if attack == "missing" else "CAPTCHA_INVALID")
        assert "token" not in result.json()


@pytest.mark.parametrize("attack", CAPTCHA_ATTACKS)
def test_change_password_requires_captcha_and_keeps_old_password(alice_client, api_client, attack):
    for captcha_fields in _attack_payloads(api_client, attack):
        payload = dict(old_password=SEED_USERS["alice"], new_password=CHANGED_PASSWORD, **captcha_fields)
        result = alice_client.session.post(alice_client.base_url + "/api/auth/change-password", json=payload, timeout=HTTP_TIMEOUT_SECONDS)
        assert result.status_code == 400
        assert result.json()["code"] == ("INVALID_PARAM" if attack == "missing" else "CAPTCHA_INVALID")
    old_login = api_client.login("alice", SEED_USERS["alice"], **_captcha(api_client))
    assert old_login.status_code == 200
    assert old_login.json()["token"]
    new_login = api_client.login("alice", CHANGED_PASSWORD, **_captcha(api_client))
    assert new_login.status_code == 401
    assert new_login.json()["code"] == "BAD_CREDENTIALS"
