# 模拟期权交易与测试

[![自动化测试](https://github.com/seanzhoujiang/options-exchange-qa-demo/actions/workflows/ci.yml/badge.svg)](https://github.com/seanzhoujiang/options-exchange-qa-demo/actions/workflows/ci.yml)

这是一个 FastAPI 模拟期权交易服务及其 API、Playwright、安全和 JMeter 测试。账户和订单只保存在进程内存中，业务规则为演示用途。

## 环境与运行

需要 Python 3.13。安装依赖和 Playwright 浏览器：

```sh
python3.13 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
PLAYWRIGHT_BROWSERS_PATH=0 ./.venv/bin/python -m playwright install chromium
```

运行 pytest 时 fixture 会自动启动带测试接口的本地服务，并在结束后停止。可分别运行 API、安全、单元和 UI 测试，或运行全部测试：

```sh
./.venv/bin/pytest -m api
./.venv/bin/pytest -m security
./.venv/bin/pytest tests/unit
./.venv/bin/pytest -m ui
./.venv/bin/pytest
./.venv/bin/pytest --collect-only -q
```

手动启动服务只用于浏览 UI、为 `BASE_URL` 提供测试目标或运行 JMeter：

```sh
env ENABLE_TEST_API=1 ./.venv/bin/uvicorn app.main:app --port 8000
```

UI 地址：`http://127.0.0.1:8000/login`。使用 `BASE_URL` 时，pytest 不管理目标服务；API、UI、安全测试每例会重置状态，请使用隔离服务并串行运行。UI 使用无界面 Chromium，失败截图写入 `test-results/`。

## 测试覆盖

| 范围 | 检查内容 | 文件 |
|---|---|---|
| 认证与账户 | 登录、验证码、改密和令牌撤销、种子账户 | `tests/api/test_auth.py`、`tests/api/test_account_market.py`、`tests/security/`、`tests/unit/test_captcha.py` |
| 行情与订单 | 合约、ticker、下单、成交、边界、状态筛选 | `tests/api/test_account_market.py`、`tests/api/test_orders.py` |
| 撤单与保证金 | 冻结释放、空头保证金、平多和净仓 | `tests/api/test_cancel.py`、`tests/api/test_margin.py`、`tests/api/test_risk_regressions.py` |
| 清算与行情推送 | 清算边界、混合持仓、用户隔离、ticker WebSocket | `tests/api/test_liquidation.py`、`tests/api/test_risk_regressions.py`、`tests/api/test_websocket.py` |
| 页面与安全 | 登录、下单、撤单、IDOR、参数篡改和测试接口门控 | `tests/ui/`、`tests/security/` |

`pytest --collect-only -q` 可查看当前测试数量和名称。

## 交易规则

价格、数量和金额使用 `Decimal`。服务端常量在 `app/config.py`；测试预期独立于应用实现，金额按规格手算。输入只接受普通十进制格式，输出为规范化定点字符串。

```text
买单保证金 = 委托价 × 数量
空头保证金 = [max(0.15 × 指数价 − 虚值额, 0.10 × 指数价) + 委托价] × 空头数量
看涨虚值额 = max(行权价 − 指数价, 0)
看跌虚值额 = max(指数价 − 行权价, 0)
维持保证金 = Σ[(0.075 × 指数价 + 标记价) × 空头数量绝对值]
权益 = 余额 + Σ(标记价 × 带符号持仓数量)
未实现盈亏 = (标记价 − 均价) × 带符号持仓数量
```

卖单先平掉同合约多仓，只有超出多仓的数量占用空头保证金。可用额为余额减挂单冻结和现有空仓初始保证金；可用额为负表示保证金不足，不代表必然清算。只有存在空仓且权益严格低于维持保证金才清算，相等时仍 active。

例如，余额 `10000` 时以 `5000` 卖出 `0.1` 张 ATM call，收到 `500` 后余额为 `10500`，持仓市值为 `-500`，权益仍为 `10000`。初始保证金为 `(15000 + 5000) × 0.1 = 2000`。标记价升到 `60000` 后，权益为 `10500 − 60000 × 0.1 = 4500`，维持保证金为 `(7500 + 60000) × 0.1 = 6750`，触发清算。

同向加仓按数量加权均价；反向成交先抵消，未反转时保留旧均价，反转后的净仓用本次成交价。改价不会撮合已有挂单。

## 安全与变异检查

安全测试直接调用 API 验证登录和改密的服务端验证码，以及 `alice`、`bob` 之间的订单访问隔离。改密会撤销该用户所有令牌，注销会撤销当前令牌。演示验证码直接包含在服务端响应中，且没有速率限制，不提供生产级防暴力尝试能力。未知用户名也会执行一次假凭证 PBKDF2，以减小响应耗时差异。

运行 `./.venv/bin/python tools/mutation_check.py` 检查测试能否发现指定实现错误。脚本先运行基线，再逐项变异并恢复源文件；存活、跳过或运行错误都会以非零状态结束。运行前取消 `BASE_URL`。

## CI 与限制

GitHub Actions 在 push 和 pull request 时运行 API、安全、单元和 UI 测试并上传 HTML 报告及截图。Job 检查名为“测试”；要阻止不通过的合并，需在仓库分支保护中将其设为必需检查。

编码过程中借助 AI 辅助，测试场景设计、验收和变异检查由本人完成。

系统没有真实订单簿、撮合引擎或期权定价模型；状态不持久化，保证金公式仅供演示。JMeter 计划尚未执行，暂无性能基准。单进程全局锁会限制并发吞吐，订单记录不会自动清理。
