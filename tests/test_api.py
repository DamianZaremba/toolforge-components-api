from unittest.mock import MagicMock
from uuid import UUID

from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from components.models.api_models import (
    DeployTokenResponse,
    HealthState,
    HealthzResponse,
    ResponseMessages,
    ToolConfigResponse,
    ToolDeploymentResponse,
)
from tests.helpers import (
    create_deploy_token,
    create_tool_config,
    create_tool_deployment,
    delete_deploy_token,
    delete_tool_config,
    get_deploy_token,
    get_fake_tool_config,
)


def test_healthz_endpoint_returns_ok_status(test_client: TestClient):
    expected_state = HealthState(status="OK")

    raw_response = test_client.get("/v1/healthz")

    assert raw_response.status_code == status.HTTP_200_OK
    gotten_state = HealthzResponse.model_validate(raw_response.json()).data
    assert gotten_state == expected_state


class TestUpdateToolConfig:
    def test_succeeds_with_valid_config(self, authenticated_client: TestClient):
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
        create_tool_config(authenticated_client)

        expected_response = ToolConfigResponse(
            messages=ResponseMessages(),
            data=get_fake_tool_config(),
        )

        response = authenticated_client.get("/v1/tool/test-tool-1/config")
        assert response.status_code == status.HTTP_200_OK

        gotten_response = ToolConfigResponse.model_validate(response.json())
        assert gotten_response == expected_response

        delete_tool_config(authenticated_client)


class TestCreateDeployment:
    def test_fails_without_auth_header(self, test_client: TestClient):
        raw_response = test_client.post("/v1/tool/test-tool-1/deployment")

        assert raw_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_fails_if_tool_has_no_config(self, authenticated_client: TestClient):
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

    def test_creates_and_returns_the_new_deployment_using_header_auth(
        self, authenticated_client: TestClient, fake_toolforge_client: MagicMock
    ):
        create_tool_config(authenticated_client)

        response = authenticated_client.post("/v1/tool/test-tool-1/deployment")
        assert response.status_code == status.HTTP_200_OK

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

    def test_creates_and_returns_the_new_deployment_using_token(
        self,
        authenticated_client: TestClient,
        fake_toolforge_client: MagicMock,
        app: FastAPI,
    ):
        create_tool_config(authenticated_client)
        token_response = create_deploy_token(authenticated_client)
        token = str(token_response.data.token)

        unauthed_client = TestClient(app)

        response = unauthed_client.post(
            f"/v1/tool/test-tool-1/deployment?token={token}"
        )
        assert response.status_code == status.HTTP_200_OK

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

    def test_returns_denied_for_bad_token(
        self,
        authenticated_client: TestClient,
        app: FastAPI,
    ):
        create_tool_config(authenticated_client)
        token_response = create_deploy_token(authenticated_client)
        token = str(token_response.data.token)

        unauthed_client = TestClient(app)

        response = unauthed_client.post(
            f"/v1/tool/test-tool-1/deployment?token={token}withextrastuff"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestDeleteDeployment:
    def test_returns_not_found_when_the_tool_does_not_exist(
        self, authenticated_client: TestClient
    ):
        response = authenticated_client.delete(
            "/v1/tool/idontexist/deployment/idontexist"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_not_found_when_the_deployment_does_not_exist(
        self, authenticated_client: TestClient
    ):
        create_tool_config(authenticated_client)

        response = authenticated_client.delete(
            "/v1/tool/test-tool-1/deployment/idontexist"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_deletes_the_deployment_when_it_exists(
        self, authenticated_client: TestClient, fake_toolforge_client: MagicMock
    ):
        create_tool_config(authenticated_client)
        deployment_response = create_tool_deployment(authenticated_client)

        delete_response = authenticated_client.delete(
            f"/v1/tool/test-tool-1/deployment/{deployment_response.data.deploy_id}"
        )
        assert delete_response.status_code == status.HTTP_200_OK


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
        my_tool_config = create_tool_config(authenticated_client)

        response = authenticated_client.delete("/v1/tool/test-tool-1/config")

        assert response.status_code == status.HTTP_200_OK
        gotten_response = ToolConfigResponse.model_validate(response.json())
        assert gotten_response.data == my_tool_config.data
        assert gotten_response.messages != []

        response = authenticated_client.get("/v1/tool/test-tool-1/config")
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestGetDeployToken:
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
        create_deploy_token(authenticated_client)

        get_response = authenticated_client.get("/v1/tool/test-tool-1/deployment/token")
        assert get_response.status_code == status.HTTP_200_OK

        delete_deploy_token(authenticated_client)


class TestCreateDeployToken:
    def test_fails_without_auth_header(self, test_client: TestClient):
        raw_response = test_client.post("/v1/tool/test-tool-1/deployment/token")
        assert raw_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_returns_the_new_token(self, authenticated_client: TestClient):
        create_response = create_deploy_token(authenticated_client)
        creation_data = DeployTokenResponse.model_validate(create_response)

        get_response = get_deploy_token(authenticated_client)
        retrieval_data = DeployTokenResponse.model_validate(get_response)

        assert creation_data.data.token == retrieval_data.data.token
        assert isinstance(creation_data.data.token, UUID)
        assert (
            "Deploy token for test-tool-1 created successfully."
            in creation_data.messages.info
        )
        assert not retrieval_data.messages.info

        delete_deploy_token(authenticated_client)


class TestDeleteDeployToken:
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
        create_response = create_deploy_token(authenticated_client)
        creation_data = DeployTokenResponse.model_validate(create_response)

        delete_response = authenticated_client.delete(
            "/v1/tool/test-tool-1/deployment/token"
        )
        assert delete_response.status_code == status.HTTP_200_OK
        deletion_data = DeployTokenResponse.model_validate(delete_response.json())
        assert deletion_data.data.token == creation_data.data.token

        get_response = authenticated_client.get("/v1/tool/test-tool-1/deployment/token")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND


class TestListDeployments:
    def test_returns_not_found_when_the_tool_does_not_exist(
        self, authenticated_client: TestClient
    ):
        response = authenticated_client.get("/v1/tool/idontexist/deployment")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_not_found_when_tool_exists_but_has_no_deployments(
        self, authenticated_client: TestClient
    ):
        create_tool_config(authenticated_client)

        response = authenticated_client.get("/v1/tool/test-tool-1/deployment")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_single_deployment_when_one_exists(
        self, authenticated_client: TestClient, fake_toolforge_client: MagicMock
    ):
        create_tool_config(authenticated_client)
        deployment_response = create_tool_deployment(authenticated_client)

        response = authenticated_client.get("/v1/tool/test-tool-1/deployment")
        assert response.status_code == status.HTTP_200_OK

        deployments = response.json()
        assert len(deployments) == 1
        assert deployments[0]["data"] == deployment_response.data.model_dump()

    def test_returns_multiple_deployments_when_they_exist(
        self, authenticated_client: TestClient, fake_toolforge_client: MagicMock
    ):
        create_tool_config(authenticated_client)
        first_deployment = create_tool_deployment(authenticated_client)
        second_deployment = create_tool_deployment(authenticated_client)

        response = authenticated_client.get("/v1/tool/test-tool-1/deployment")
        assert response.status_code == status.HTTP_200_OK

        deployments = response.json()
        assert len(deployments) == 2
        deployment_ids = {dep["data"]["deploy_id"] for dep in deployments}
        assert deployment_ids == {
            first_deployment.data.deploy_id,
            second_deployment.data.deploy_id,
        }
