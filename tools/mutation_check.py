from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as ET

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTEST_TEST_FAILURE = 1


@dataclass(frozen=True)
class Mutation:
    name: str
    path: str
    original: str
    replacement: str


MUTATIONS = (
    Mutation("空头保证金率降低", "app/config.py",
             'SHORT_MARGIN_RATE = Decimal("0.15")', 'SHORT_MARGIN_RATE = Decimal("0.12")'),
    Mutation("维持保证金率降低", "app/config.py",
             'MAINTENANCE_MARGIN_RATE = Decimal("0.075")', 'MAINTENANCE_MARGIN_RATE = Decimal("0.05")'),
    Mutation("最小价格单位降低", "app/config.py",
             'PRICE_TICK = Decimal("0.5")', 'PRICE_TICK = Decimal("0.1")'),
    Mutation("移除订单所有者校验", "app/trading.py",
             '    if order is None or order["username"] != username:\n', '    if order is None:\n'),
    Mutation("登录跳过验证码", "app/main.py",
             'def login(body: Login):\n    with store.lock:\n        auth.verify_captcha(body.captcha_id, body.captcha_code)\n',
             'def login(body: Login):\n    with store.lock:\n'),
    # 状态照常变为 cancelled，但仍占用冻结金额。
    Mutation("撤单不释放冻结金额", "app/trading.py",
             'if order["username"] == username and order["status"] == "open"), ZERO)',
             'if order["username"] == username and order["status"] in ("open", "cancelled")), ZERO)'),
    Mutation("换密跳过旧密码校验", "app/main.py",
             '    if not verify_password(credentials, body.old_password):\n        auth.fail(401, "BAD_CREDENTIALS", "原密码错误")\n', ''),
    Mutation("清算错误包含相等边界", "app/risk.py",
             'and summary["equity"] < summary["maintenance_margin"]:',
             'and summary["equity"] <= summary["maintenance_margin"]:'),
    Mutation("冻结金额未按用户隔离", "app/trading.py",
             'if order["username"] == username and order["status"] == "open"), ZERO)',
             'if order["status"] == "open"), ZERO)'),
    Mutation("改价遗漏指数更新", "app/risk.py",
             '    store.index_price = index\n', '    # 变异：遗漏指数更新。\n'),
    Mutation("清算仅关闭空仓", "app/risk.py",
             '            user["positions"].clear()\n',
             '            user["positions"] = {name: position for name, position in user["positions"].items() if position["quantity"] > ZERO}\n'),
)


def run_suite(artifact_path):
    environment = os.environ.copy()
    # 独立缓存目录，避免同秒、同长度修改误读旧字节码。
    environment["PYTHONPYCACHEPREFIX"] = str(artifact_path / "bytecode")
    report_path = artifact_path / "results.xml"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "not ui", "-q", "-x", f"--junitxml={report_path}"],
        cwd=PROJECT_ROOT, env=environment, check=False,
    )
    return result.returncode, report_path


def classify(returncode, report_path):
    if returncode == 0:
        return "SURVIVED"
    if returncode == PYTEST_TEST_FAILURE and report_path.exists():
        try:
            suites = ET.parse(report_path).getroot().iter("testsuite")
            counts = [(int(suite.get("failures", "0")), int(suite.get("errors", "0"))) for suite in suites]
            if sum(failures for failures, errors in counts) > 0 and sum(errors for failures, errors in counts) == 0:
                return "KILLED"
        except (ET.ParseError, ValueError, OSError):
            pass
    return "ERROR"


def main():
    if os.environ.get("BASE_URL"):
        print("ERROR：变异必须测试本地新进程，请先取消 BASE_URL。", flush=True)
        return 1
    outcomes = []
    with TemporaryDirectory(prefix="options-mutation-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        print("先执行未变异基线检查", flush=True)
        baseline_code, _ = run_suite(temporary_path / "baseline")
        if baseline_code != 0:
            print("ERROR：基线未通过，不进行变异。", flush=True)
            return 1
        for mutation_index, mutation in enumerate(MUTATIONS):
            source_path = PROJECT_ROOT / mutation.path
            original_bytes = source_path.read_bytes()
            original_source = original_bytes.decode("utf-8")
            occurrence_count = original_source.count(mutation.original)
            if occurrence_count != 1:
                outcomes.append((mutation.name, "SKIPPED"))
                print(f"SKIPPED：{mutation.name}，目标片段出现 {occurrence_count} 次。", flush=True)
                continue
            try:
                source_path.write_bytes(original_source.replace(mutation.original, mutation.replacement, 1).encode("utf-8"))
                print(f"检查变异：{mutation.name}", flush=True)
                returncode, report_path = run_suite(temporary_path / f"mutant-{mutation_index}")
                outcome = classify(returncode, report_path)
            finally:
                source_path.write_bytes(original_bytes)
            outcomes.append((mutation.name, outcome))
            print(f"{outcome}：{mutation.name}", flush=True)
    print("变异结果：", flush=True)
    for name, outcome in outcomes:
        print(f"{outcome}：{name}", flush=True)
    # 跳过和运行错误不能算作杀死变异。
    return 0 if all(outcome == "KILLED" for name, outcome in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
