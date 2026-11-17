import secrets
import time
from fastapi import HTTPException
from . import store
from .config import CAPTCHA_DIGITS, CAPTCHA_TTL_SECONDS


def fail(status, code, message, field=None):
    detail = dict(code=code, message=message)
    if field:
        detail["field"] = field
    raise HTTPException(status_code=status, detail=detail)


def create_captcha():
    captcha_id = secrets.token_urlsafe()
    captcha_code = "".join(str(secrets.randbelow(10)) for _ in range(CAPTCHA_DIGITS))
    now = time.monotonic()
    for expired_id in list(store.captchas):
        if store.captchas[expired_id][1] <= now:
            del store.captchas[expired_id]
    store.captchas[captcha_id] = (captcha_code, now + CAPTCHA_TTL_SECONDS)
    # 演示没有短信或邮件通道，直接返回验证码。
    return dict(captcha_id=captcha_id, captcha_code=captcha_code)


def verify_captcha(captcha_id, captcha_code):
    saved = store.captchas.pop(captcha_id, None)
    if saved is None or saved[1] <= time.monotonic() or not secrets.compare_digest(saved[0].encode(), captcha_code.encode()):
        fail(400, "CAPTCHA_INVALID", "验证码无效、已过期或已使用", "captcha_code")


def authenticate(authorization):
    if not authorization or not authorization.startswith("Bearer "):
        fail(401, "UNAUTHORIZED", "请先登录")
    username = store.tokens.get(authorization[7:])
    if username is None:
        fail(401, "UNAUTHORIZED", "登录凭证无效")
    return username


def revoke_tokens(username):
    """调用方持锁。"""
    for token, owner in list(store.tokens.items()):
        if owner == username:
            del store.tokens[token]
