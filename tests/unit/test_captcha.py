import pytest
from fastapi import HTTPException
from app import auth, store

# 有效期预期独立取自规格，不跟随应用配置变化。
CAPTCHA_TTL_SECONDS = 60
CLOCK_START_SECONDS = 1000.0
BEFORE_EXPIRY_SECONDS = 0.001


@pytest.mark.parametrize("at_expiry", [False, True], ids=["before-expiry", "at-expiry"])
def test_captcha_expiry_boundary(monkeypatch, at_expiry):
    monkeypatch.setattr(auth.time, "monotonic", lambda: CLOCK_START_SECONDS)
    with store.lock:
        previous_captchas = store.captchas.copy()
        store.captchas.clear()
        try:
            captcha = auth.create_captcha()
            current_time = CLOCK_START_SECONDS + CAPTCHA_TTL_SECONDS
            if not at_expiry:
                current_time -= BEFORE_EXPIRY_SECONDS
            monkeypatch.setattr(auth.time, "monotonic", lambda: current_time)
            if at_expiry:
                with pytest.raises(HTTPException) as error:
                    auth.verify_captcha(**captcha)
                assert error.value.status_code == 400
                assert error.value.detail["code"] == "CAPTCHA_INVALID"
            else:
                auth.verify_captcha(**captcha)
            assert captcha["captcha_id"] not in store.captchas
        finally:
            store.captchas.clear()
            store.captchas.update(previous_captchas)
