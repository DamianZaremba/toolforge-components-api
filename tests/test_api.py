from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from toolforge_weld.api_client import ToolforgeClient
from toolforge_weld.kubernetes_config import Kubeconfig

import components.deploy_task
from components.main import create_app
from components.models.api_models import (
    DeploymentTokenResponse,
    HealthState,
    HealthzResponse,
    ResponseMessages,
    ToolConfig,
    ToolConfigResponse,
    ToolDeploymentResponse,
)
from components.settings import Settings


@pytest.fixture
def test_client():
    app = create_app(settings=Settings(log_level="debug"))
    with TestClient(app) as client:
        yield client


@pytest.fixture
def authenticated_client(test_client) -> TestClient:
    test_client.headers.update({"x-toolforge-tool": "test-tool-1"})
    return test_client


@pytest.fixture
def fake_toolforge_client(monkeypatch) -> ToolforgeClient:
    fake_kube_config = Kubeconfig(
        current_namespace="",
        current_server="",
    )

    monkeypatch.setattr(Kubeconfig, "load", lambda *args, **kwargs: fake_kube_config)
    fake_client = MagicMock(spec=ToolforgeClient)

    monkeypatch.setattr(
        components.deploy_task, "ToolforgeClient", lambda *args, **kwargs: fake_client
    )

    return fake_client


def get_fake_tool_config(**overrides) -> ToolConfig:
    params = {
        "config_version": "v1",
        "components": {
            "component1": {
                "build": {"use_prebuilt": "silly_image"},
                "component_type": "continuous",
                "run": {"command": "some command"},
            }
        },
    }
    params.update(overrides)
    return ToolConfig.model_validate(params)


def test_healthz_endpoint_returns_ok_status(test_client: TestClient):
    expected_state = HealthState(status="OK")

    raw_response = test_client.get("/v1/healthz")

    assert raw_response.status_code == status.HTTP_200_OK
    gotten_state = HealthzResponse.model_validate(raw_response.json()).data
    assert gotten_state == expected_state


class TestUpdateToolConfig:
    def test_succeeds_with_valid_config(
        self,
        authenticated_client: TestClient,
    ):
        expected_tool_config = get_fake_tool_config()
        raw_response = authenticated_client.post(
            "/v1/tool/test-tool-1/config",
            content=expected_tool_config.model_dump_json(),
        )

        assert raw_response.status_code == status.HTTP_200_OK
        gotten_response = ToolConfigResponse.model_validate(raw_response.json())
        assert gotten_response.data == expected_tool_config
        assert gotten_response.messages != []

    def test_fails_with_invalid_config_data(
        self,
        authenticated_client: TestClient,
    ):
        raw_response = authenticated_client.post(
            "/v1/tool/test-tool-1/config", content=""
        )

        assert raw_response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_fails_without_auth_header(self, test_client: TestClient):
        expected_tool_config = get_fake_tool_config()
        raw_response = test_client.post(
            "/v1/tool/test-tool-1/config",
            content=expected_tool_config.model_dump_json(),
        )

        assert raw_response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetToolConfig:
    def test_returns_not_found_when_tool_does_not_exist(
        self,
        authenticated_client: TestClient,
    ):
        raw_response = authenticated_client.get("/v1/tool/idontexist/config")

        assert raw_response.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieves_the_set_config(self, authenticated_client: TestClient):
        my_tool_config = get_fake_tool_config()
        expected_response = ToolConfigResponse(
            messages=ResponseMessages(),
            data=my_tool_config,
        )
        response = authenticated_client.post(
            "/v1/tool/test-tool-1/config", content=my_tool_config.model_dump_json()
        )
        response.raise_for_status()

        response = authenticated_client.get("/v1/tool/test-tool-1/config")

        assert response.status_code == status.HTTP_200_OK
        gotten_response = ToolConfigResponse.model_validate(response.json())
        assert gotten_response == expected_response


class TestCreateDeployment:
    def test_fails_without_auth_header(self, test_client: TestClient):
        raw_response = test_client.post("/v1/tool/test-tool-1/deployment")

        assert raw_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_fails_if_tool_has_no_config(self, authenticated_client: TestClient):
        authenticated_client.delete("/v1/tool/test-tool-1/config")
        raw_response = authenticated_client.get("/v1/tool/test-tool-1/config")
        assert raw_response.status_code == status.HTTP_404_NOT_FOUND

        raw_response = authenticated_client.post("/v1/tool/test-tool-1/deployment")

        assert raw_response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_not_found_when_tool_does_not_exist(
        self,
        authenticated_client: TestClient,
    ):
        raw_response = authenticated_client.post("/v1/tool/idontexist/deployment")

        assert raw_response.status_code == status.HTTP_404_NOT_FOUND

    def test_creates_and_returns_the_new_deployment(
        self, authenticated_client: TestClient, fake_toolforge_client: MagicMock
    ):
        my_tool_config = get_fake_tool_config()
        response = authenticated_client.post(
            "/v1/tool/test-tool-1/config", content=my_tool_config.model_dump_json()
        )
        response.raise_for_status()

        response = authenticated_client.post("/v1/tool/test-tool-1/deployment")
        response.raise_for_status()

        expected_deployment = ToolDeploymentResponse.model_validate(response.json())

        response = authenticated_client.get(
            f"/v1/tool/test-tool-1/deployment/{expected_deployment.data.deploy_id}"
        )

        assert response.status_code == status.HTTP_200_OK
        gotten_deployment = ToolDeploymentResponse.model_validate(response.json())
        # we kinda ignore the messages
        assert expected_deployment.data == gotten_deployment.data

        fake_toolforge_client.post.assert_called_once_with(
            "/jobs/v1/tool/test-tool-1/jobs/",
            json={
                "cmd": "some command",
                "continuous": True,
                "name": "component1",
                "imagename": "silly_image",
            },
            verify=True,
        )


class TestDeleteToolConfig:
    def test_fails_when_config_does_not_exist(
        self,
        authenticated_client: TestClient,
    ):
        response = authenticated_client.delete("/v1/tool/nonexistent-tool/config")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        json_response = response.json()
        assert "data" not in json_response
        assert (
            "No configuration found for tool: nonexistent-tool"
            in json_response["messages"]["error"]
        )

    def test_succeeds_when_config_exists(
        self,
        authenticated_client: TestClient,
    ):
        my_tool_config = get_fake_tool_config()
        response = authenticated_client.post(
            "/v1/tool/test-tool-1/config", content=my_tool_config.model_dump_json()
        )
        response.raise_for_status()

        response = authenticated_client.delete("/v1/tool/test-tool-1/config")

        assert response.status_code == status.HTTP_200_OK
        gotten_response = ToolConfigResponse.model_validate(response.json())
        assert gotten_response.data == my_tool_config
        assert gotten_response.messages != []

        response = authenticated_client.get("/v1/tool/test-tool-1/config")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestGetDeploymentToken:
    def test_fails_without_auth_header(self, test_client: TestClient):
        raw_response = test_client.get("/v1/tool/test-tool-1/deployment/token")

        assert raw_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_returns_not_found_when_token_does_not_exist(
        self, authenticated_client: TestClient
    ):
        raw_response = authenticated_client.get(
            "/v1/tool/test-tool-no-token/deployment/token"
        )

        assert raw_response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_the_token_when_it_exists(self, authenticated_client: TestClient):
        create_response = authenticated_client.post(
            "/v1/tool/test-tool-1/deployment/token"
        )
        assert create_response.status_code == status.HTTP_200_OK

        get_response = authenticated_client.get("/v1/tool/test-tool-1/deployment/token")
        assert get_response.status_code == status.HTTP_200_OK

        # clean up
        authenticated_client.delete("/v1/tool/test-tool-1/deployment/token")


class TestCreateDeploymentToken:
    def test_fails_without_auth_header(self, test_client: TestClient):
        raw_response = test_client.post("/v1/tool/test-tool-1/deployment/token")
        assert raw_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_returns_the_new_token(self, authenticated_client: TestClient):
        create_response = authenticated_client.post(
            "/v1/tool/test-tool-1/deployment/token"
        )
        assert create_response.status_code == status.HTTP_200_OK
        creation_data = DeploymentTokenResponse.model_validate(create_response.json())

        get_response = authenticated_client.get("/v1/tool/test-tool-1/deployment/token")
        assert get_response.status_code == status.HTTP_200_OK
        retrieval_data = DeploymentTokenResponse.model_validate(get_response.json())

        assert creation_data.data.token == retrieval_data.data.token
        assert isinstance(creation_data.data.token, UUID)
        assert (
            "Deployment token for test-tool-1 created successfully."
            in creation_data.messages.info
        )
        assert not retrieval_data.messages.info

        # clean up
        authenticated_client.delete("/v1/tool/test-tool-1/deployment/token")


class TestDeleteDeploymentToken:
    def test_fails_without_auth_header(self, test_client: TestClient):
        raw_response = test_client.delete("/v1/tool/test-tool-1/deployment/token")

        assert raw_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_returns_not_found_when_tool_does_not_exist(
        self, authenticated_client: TestClient
    ):
        raw_response = authenticated_client.delete(
            "/v1/tool/idontexist/deployment/token"
        )

        assert raw_response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_not_found_when_token_does_not_exist(
        self, authenticated_client: TestClient
    ):
        expected_tool_config = get_fake_tool_config()
        raw_response = authenticated_client.post(
            "/v1/tool/test-tool-1/config",
            content=expected_tool_config.model_dump_json(),
        )

        assert raw_response.status_code == status.HTTP_200_OK
        token_response = authenticated_client.delete(
            "/v1/tool/test-tool-1/deployment/token"
        )
        assert token_response.status_code == status.HTTP_404_NOT_FOUND

    def test_deletes_the_token_when_it_exists(self, authenticated_client: TestClient):
        pass
        # create a token
        create_response = authenticated_client.post(
            "/v1/tool/test-tool-1/deployment/token"
        )
        assert create_response.status_code == status.HTTP_200_OK

        # get the token
        get_response = authenticated_client.get("/v1/tool/test-tool-1/deployment/token")
        assert get_response.status_code == status.HTTP_200_OK

        # delete the token
        delete_response = authenticated_client.delete(
            "/v1/tool/test-tool-1/deployment/token"
        )
        assert delete_response.status_code == status.HTTP_200_OK

        # try to get the token again
        get_response = authenticated_client.get("/v1/tool/test-tool-1/deployment/token")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND
