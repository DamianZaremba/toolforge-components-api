import logging
from typing import Generator
from unittest.mock import MagicMock

import kubernetes
import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from toolforge_weld.api_client import ToolforgeClient
from toolforge_weld.kubernetes_config import Kubeconfig

import components.deploy_task
import components.runtime.toolforge
import components.settings
from components.main import create_app
from components.settings import Settings
from components.storage.utils import get_storage

logger = logging.getLogger(__name__)


@pytest.fixture
def app() -> FastAPI:
    settings = Settings(log_level="debug", runtime_type="toolforge")
    components.settings.settings = settings
    app = create_app(settings=settings)
    # force creating a new storage
    get_storage(settings=settings, rebuild_storage=True)
    return app


@pytest.fixture
def test_client(app) -> Generator[TestClient, None, None]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def authenticated_client(test_client) -> TestClient:
    test_client.headers.update({"x-toolforge-tool": "test-tool-1"})
    return test_client


@pytest.fixture
def fake_toolforge_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake_kube_config = Kubeconfig(
        current_namespace="",
        current_server="",
    )

    monkeypatch.setattr(Kubeconfig, "load", lambda *args, **kwargs: fake_kube_config)
    fake_client = MagicMock(spec=ToolforgeClient)

    monkeypatch.setattr(
        components.runtime.toolforge, "get_toolforge_client", lambda: fake_client
    )

    return fake_client


@pytest.fixture(autouse=True)
def cleanup_deployments(app: FastAPI):
    yield
    client = TestClient(app)
    client.headers.update({"x-toolforge-tool": "test-tool-1"})
    response = client.get("/v1/tool/test-tool-1/deployment")
    if response.status_code == status.HTTP_200_OK:
        deployments = response.json()
        for deployment in deployments["data"]["deployments"]:
            client.delete(f"/v1/tool/test-tool-1/deployment/{deployment['deploy_id']}")


@pytest.fixture(autouse=True)
def mock_time_sleep(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(components.deploy_task, "time", MagicMock())
    yield
    monkeypatch.undo()


@pytest.fixture
def storage_k8s_cli(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    k8s_mock = MagicMock(spec=kubernetes)
    monkeypatch.setattr("components.storage.kubernetes.kubernetes", k8s_mock)
    return k8s_mock.client.CustomObjectsApi()
