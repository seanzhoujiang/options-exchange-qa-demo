from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import requests
from .test_data import (
    LOCAL_HOST, SERVER_POLL_INTERVAL_SECONDS, SERVER_START_TIMEOUT_SECONDS,
    SERVER_STOP_TIMEOUT_SECONDS,
)


@contextmanager
def running_server(enable_test_api=True):
    with socket.socket() as listener:
        listener.bind((LOCAL_HOST, 0))
        port = listener.getsockname()[1]
    environment = os.environ.copy()
    environment.pop("ENABLE_TEST_API", None)
    if enable_test_api:
        environment["ENABLE_TEST_API"] = "1"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", LOCAL_HOST, "--port", str(port)],
        cwd=Path(__file__).resolve().parents[2], env=environment,
    )
    server_url = f"http://{LOCAL_HOST}:{port}"
    deadline = time.monotonic() + SERVER_START_TIMEOUT_SECONDS
    try:
        with requests.Session() as session:
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"服务提前退出，退出码：{process.returncode}")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError("等待服务启动超时")
                try:
                    if session.get(server_url + "/login", timeout=min(remaining, SERVER_POLL_INTERVAL_SECONDS)).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(SERVER_POLL_INTERVAL_SECONDS)
        yield server_url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=SERVER_STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=SERVER_STOP_TIMEOUT_SECONDS)
