import asyncio
import json
import os
import secrets
from decimal import Decimal
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, field_validator
from . import auth, store, trading, risk
from .config import PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH, WS_SEND_TIMEOUT_SECONDS
from .passwords import DUMMY_CREDENTIALS, credential_snapshot, password_credentials, verify_password


class PlainDecimalRequest(Request):
    async def json(self):
        # 保留原始写法，避免 JSON 把 1e2 先转成 100.0。
        if not hasattr(self, "_plain_decimal_json"):
            self._plain_decimal_json = json.loads(await self.body(), parse_float=str)
        return self._plain_decimal_json


class PlainDecimalRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request):
            return await handler(PlainDecimalRequest(request.scope, request.receive))
        return handle

app = FastAPI(title="期权交易演示")
app.router.route_class = PlainDecimalRoute
static_path = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")
clients = set()


def json_value(value):
    if isinstance(value, Decimal):
        if value.is_zero():
            return "0"
        rendered = format(value, "f")
        return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_value(item) for item in value]
    return value


def response(value):
    return JSONResponse(json_value(value))


@app.exception_handler(StarletteHTTPException)
async def http_error(request, exception):
    detail = exception.detail if isinstance(exception.detail, dict) else dict(code="NOT_FOUND" if exception.status_code == 404 else "HTTP_ERROR", message="请求资源不可用")
    return JSONResponse(detail, status_code=exception.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exception):
    error = exception.errors()[0]
    field = str(error["loc"][1] if len(error["loc"]) > 1 else error["loc"][0])
    try:
        field.encode("utf-8")
    except UnicodeEncodeError:
        field = "body"
    return JSONResponse(dict(code="INVALID_PARAM", message="参数缺失或格式无效", field=field), status_code=400)


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*")
    @classmethod
    def validate_encodable_text(cls, value):
        if isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                raise ValueError("文本包含无效的 Unicode 字符") from None
        return value


class Login(InputModel):
    username: str
    password: str
    captcha_id: str
    captcha_code: str


class PasswordChange(InputModel):
    old_password: str
    new_password: str
    captcha_id: str
    captcha_code: str


class OrderInput(InputModel):
    instrument: str
    side: str
    price: str | int | float
    quantity: str | int | float


class MarkInput(InputModel):
    instrument: str
    mark_price: str | int | float
    index_price: str | int | float | None = None


def username_for(request):
    return auth.authenticate(request.headers.get("authorization"))


@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse("/login")


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(static_path / "login.html")


@app.get("/trade", include_in_schema=False)
def trade_page():
    return FileResponse(static_path / "trade.html")


@app.post("/api/auth/captcha")
def captcha():
    with store.lock:
        return response(auth.create_captcha())


@app.post("/api/auth/login")
def login(body: Login):
    with store.lock:
        auth.verify_captcha(body.captcha_id, body.captcha_code)
        user = store.users.get(body.username)
        credentials = credential_snapshot(user) if user is not None else DUMMY_CREDENTIALS
    password_valid = verify_password(credentials, body.password)
    with store.lock:
        # 防止哈希期间的重置或换密让旧凭证继续签发令牌。
        if not password_valid or user is None or store.users.get(body.username) is not user or user["password_hash"] != credentials["password_hash"]:
            auth.fail(401, "BAD_CREDENTIALS", "用户名或密码错误")
        token = secrets.token_urlsafe()
        store.tokens[token] = body.username
        return response(dict(token=token))


@app.post("/api/auth/change-password")
def change_password(body: PasswordChange, request: Request):
    with store.lock:
        username = username_for(request)
        auth.verify_captcha(body.captcha_id, body.captcha_code)
        user = store.users[username]
        credentials = credential_snapshot(user)
    if not verify_password(credentials, body.old_password):
        auth.fail(401, "BAD_CREDENTIALS", "原密码错误")
    if not PASSWORD_MIN_LENGTH <= len(body.new_password) <= PASSWORD_MAX_LENGTH:
        auth.fail(400, "INVALID_PARAM", "新密码长度必须为8到64个字符", "new_password")
    updated_credentials = password_credentials(body.new_password)
    with store.lock:
        username_for(request)
        if store.users.get(username) is not user or user["password_hash"] != credentials["password_hash"]:
            auth.fail(401, "BAD_CREDENTIALS", "凭证已变更，请重新登录")
        user.update(updated_credentials)
        auth.revoke_tokens(username)
        return response(dict(message="密码已修改"))


@app.post("/api/auth/logout")
def logout(request: Request):
    with store.lock:
        username_for(request)
        del store.tokens[request.headers["authorization"][7:]]
        return response(dict(message="已退出登录"))


@app.get("/api/account")
def account(request: Request):
    with store.lock:
        return response(trading.account(username_for(request)))


@app.get("/api/instruments")
def instruments():
    with store.lock:
        return response(list(store.instruments.values()))


@app.get("/api/market/ticker/{instrument}")
def ticker(instrument: str):
    with store.lock:
        trading.instrument_named(instrument)
        return response(risk.ticker(instrument))


@app.post("/api/orders")
def place_order(body: OrderInput, request: Request):
    with store.lock:
        return response(trading.place(username_for(request), **body.model_dump()))


@app.get("/api/orders")
def orders(request: Request, status: str | None = None):
    with store.lock:
        username = username_for(request)
        if status is not None and status not in ("open", "filled", "cancelled"):
            auth.fail(400, "INVALID_PARAM", "订单状态无效", "status")
        return response([order for order in store.orders.values() if order["username"] == username and (status is None or order["status"] == status)])


@app.get("/api/orders/{order_id}")
def get_order(order_id: str, request: Request):
    with store.lock:
        return response(trading.owned_order(username_for(request), order_id))


@app.delete("/api/orders/{order_id}")
def cancel_order(order_id: str, request: Request):
    with store.lock:
        return response(trading.cancel(username_for(request), order_id))


@app.get("/api/positions")
def positions(request: Request):
    with store.lock:
        return response(trading.positions(username_for(request)))


@app.get("/api/liquidations")
def liquidations(request: Request):
    with store.lock:
        return response(store.users[username_for(request)]["liquidations"])


async def broadcast(tickers):
    async def send_updates(client):
        try:
            for update in tickers:
                await asyncio.wait_for(client.send_json(json_value(update)), timeout=WS_SEND_TIMEOUT_SECONDS)
        except (TimeoutError, RuntimeError, WebSocketDisconnect, OSError):
            clients.discard(client)
    await asyncio.gather(*(send_updates(client) for client in list(clients)))


if os.getenv("ENABLE_TEST_API") == "1":
    @app.post("/api/test/reset")
    def reset(background_tasks: BackgroundTasks):
        with store.lock:
            store.reset()
            snapshot = [risk.ticker(name) for name in store.instruments]
        background_tasks.add_task(broadcast, snapshot)
        return response(dict(message="状态已重置"))

    @app.post("/api/test/mark-price")
    def mark_price(body: MarkInput, background_tasks: BackgroundTasks):
        with store.lock:
            update = risk.update_price(body.instrument, body.mark_price, body.index_price)
            updates = [risk.ticker(name) for name in store.instruments] if body.index_price is not None else [update]
        background_tasks.add_task(broadcast, updates)
        return response(update)


@app.websocket("/ws/ticker")
async def websocket_ticker(websocket: WebSocket):
    await websocket.accept()
    with store.lock:
        snapshot = [risk.ticker(name) for name in store.instruments]
    clients.add(websocket)
    try:
        await websocket.send_json(json_value(snapshot))
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass
    finally:
        clients.discard(websocket)
