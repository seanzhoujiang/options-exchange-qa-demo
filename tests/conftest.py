import os
import pytest
from tests.support.api_client import ApiClient
from tests.support.test_data import SEED_USERS
from tests.support.server import running_server


@pytest.fixture(scope="session")
def base_url():
    external_url = os.getenv("BASE_URL")
    if external_url:
        yield external_url.rstrip("/")
        return
    with running_server(enable_test_api=True) as server_url:
        yield server_url


@pytest.fixture
def api_client(base_url):
    client = ApiClient(base_url)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture(autouse=True)
def reset_state(request):
    if any(request.node.get_closest_marker(marker) is not None for marker in ("api", "ui", "security")):
        client = request.getfixturevalue("api_client")
        result = client.reset()
        assert result.status_code == 200, result.text
        assert result.json()["message"] == "状态已重置"


@pytest.fixture
def login_as(base_url, reset_state):
    clients = []
    def authenticate(username):
        client = ApiClient(base_url)
        clients.append(client)
        captcha_response = client.get_captcha()
        assert captcha_response.status_code == 200, captcha_response.text
        result = client.login(username, SEED_USERS[username], **captcha_response.json())
        assert result.status_code == 200, result.text
        assert isinstance(result.json()["token"], str) and result.json()["token"]
        client.session.headers["Authorization"] = "Bearer " + result.json()["token"]
        return client
    try:
        yield authenticate
    finally:
        for client in clients:
            client.close()


@pytest.fixture
def alice_client(login_as):
    return login_as("alice")


@pytest.fixture
def bob_client(login_as):
    return login_as("bob")
