import logging
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from toolforge_weld.api_client import ToolforgeClient
from toolforge_weld.kubernetes_config import Kubeconfig

import components.deploy_task
from components.main import create_app
from components.settings import Settings

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def app():
    settings = Settings(log_level="debug")
    app = create_app(settings=settings)
    return app


@pytest.fixture
def test_client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def authenticated_client(test_client) -> TestClient:
    test_client.headers.update({"x-toolforge-tool": "test-tool-1"})
    return test_client


@pytest.fixture
def fake_toolforge_client(monkeypatch) -> MagicMock:
    fake_kube_config = Kubeconfig(
        current_namespace="",
        current_server="",
    )

    monkeypatch.setattr(Kubeconfig, "load", lambda *args, **kwargs: fake_kube_config)
    fake_client = MagicMock(spec=ToolforgeClient)

    monkeypatch.setattr(
        components.deploy_task, "get_toolforge_client", lambda: fake_client
    )

    return fake_client
