from threading import Lock
from decimal import Decimal
from .config import EXPIRY, SEED_BALANCE, SEED_INDEX_PRICE, SEED_OPTIONS, SEED_PASSWORDS
from .passwords import password_credentials

lock = Lock()
users = {}
tokens = {}
captchas = {}
instruments = {}
orders = {}
# 启动时算好种子凭证，避免重置持锁做哈希。
seed_credentials = {username: password_credentials(password) for username, password in SEED_PASSWORDS.items()}
index_price = SEED_INDEX_PRICE


def reset():
    """调用方持锁；重置会撤销全部令牌。"""
    global index_price
    users.clear()
    tokens.clear()
    captchas.clear()
    orders.clear()
    instruments.clear()
    index_price = SEED_INDEX_PRICE
    for username, credentials in seed_credentials.items():
        users[username] = dict(**credentials, balance=SEED_BALANCE,
                               status="active", positions={}, liquidations=[])
    for strike, option_type, premium in SEED_OPTIONS:
        suffix = "C" if option_type == "call" else "P"
        name = f"BTC-20261231-{strike}-{suffix}"
        instruments[name] = dict(name=name, underlying="BTC", strike=Decimal(strike),
                                 option_type=option_type, expiry=EXPIRY,
                                 mark_price=Decimal(premium))


with lock:
    reset()
