import pytest
from tests.support.api_client import ApiClient
from tests.support.server import running_server
from tests.support.test_data import ATM_CALL

pytestmark = pytest.mark.security


def test_test_routes_hidden_by_default():
    # 无论 BASE_URL 指向哪里，均额外启动一个显式移除开关的本地进程。
    with running_server(enable_test_api=False) as server_url:
        client = ApiClient(server_url)
        try:
            for result in (client.reset(), client.set_mark_price(ATM_CALL, "60000")):
                assert result.status_code == 404
                assert result.json() == {"code": "NOT_FOUND", "message": "请求资源不可用"}
        finally:
            client.close()
