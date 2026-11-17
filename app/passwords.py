import hashlib
import hmac
import secrets
from .config import PASSWORD_HASH_ITERATIONS, PASSWORD_SALT_BYTES


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_HASH_ITERATIONS)


def password_credentials(password):
    salt = secrets.token_bytes(PASSWORD_SALT_BYTES)
    return dict(password_salt=salt, password_hash=hash_password(password, salt))


def verify_password(user, password):
    return hmac.compare_digest(user["password_hash"], hash_password(password, user["password_salt"]))


# 不存在的用户也做一次哈希，减小耗时差异。
DUMMY_SALT = bytes(PASSWORD_SALT_BYTES)
DUMMY_CREDENTIALS = dict(password_salt=DUMMY_SALT, password_hash=hash_password("dummy-password", DUMMY_SALT))


def credential_snapshot(user):
    return dict(password_salt=user["password_salt"], password_hash=user["password_hash"])
