from unittest.mock import ANY, MagicMock
from uuid import UUID

import pytest
from fastapi import BackgroundTasks, FastAPI, status
from fastapi.testclient import TestClient

from components.gen.toolforge_models import BuildsBuildStatus, JobsJobResponse
from components.models.api_models import (
    Deployment,
    DeploymentBuildInfo,
    DeploymentBuildState,
    DeploymentRunState,
    DeploymentState,
    DeployTokenResponse,
    HealthState,
    HealthzResponse,
    ResponseMessages,
    ToolConfigResponse,
    ToolDeploymentResponse,
)
from components.settings import get_settings
from components.storage.mock import MockStorage
from tests.helpers import (
    create_deploy_token,
    create_tool_config,
    create_tool_deployment,
    delete_deploy_token,
    delete_tool_config,
    get_deploy_token,
    get_fake_tool_config,
)
from tests.testlibs import get_defined_job


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
        BETA_WARNING_MESSAGE = "You are using a beta feature of Toolforge."

        expected_response = ToolConfigResponse(
            messages=ResponseMessages(warning=[BETA_WARNING_MESSAGE]),
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

    def test_creates_and_returns_the_new_deployment_of_prebuilt_job_using_header_auth(
        self, authenticated_client: TestClient, fake_toolforge_client: MagicMock
    ):
        create_tool_config(authenticated_client)
        fake_toolforge_client.patch.return_value = JobsJobResponse(
            job=get_defined_job(), messages=None
        ).model_dump()

        response = authenticated_client.post("/v1/tool/test-tool-1/deployment")
        assert response.status_code == status.HTTP_200_OK

        expected_deployment = ToolDeploymentResponse.model_validate(response.json())
        expected_deployment.data.status = DeploymentState.successful
        expected_deployment.data.long_status = ANY
        expected_deployment.data.builds[
            "component1"
        ].build_status = DeploymentBuildState.successful
        expected_deployment.data.builds[
            "component1"
        ].build_id = DeploymentBuildInfo.NO_BUILD_NEEDED
        expected_deployment.data.runs[
            "component1"
        ].run_status = DeploymentRunState.successful
        expected_deployment.data.runs["component1"].run_long_status = ANY

        response = authenticated_client.get(
            f"/v1/tool/test-tool-1/deployment/{expected_deployment.data.deploy_id}"
        )

        assert response.status_code == status.HTTP_200_OK
        gotten_deployment = ToolDeploymentResponse.model_validate(response.json())
        # we kinda ignore the messages
        assert expected_deployment.data == gotten_deployment.data

        fake_toolforge_client.patch.assert_called_once_with(
            "/jobs/v1/tool/test-tool-1/jobs/",
            json={
                "cmd": "some command",
                "continuous": True,
                "name": "component1",
                "imagename": "tool-test-tool-1/silly_image:latest",
            },
            verify=True,
        )

    @pytest.mark.asyncio
    async def test_creates_and_returns_the_new_deployment_using_token(
        self,
        authenticated_client: TestClient,
        fake_toolforge_client: MagicMock,
        app: FastAPI,
    ):
        create_tool_config(authenticated_client)
        token_response = create_deploy_token(authenticated_client)
        token = str(token_response.data.token)

        fake_toolforge_client.patch.return_value = JobsJobResponse(
            job=get_defined_job(), messages=None
        ).model_dump()
        unauthed_client = TestClient(app)

        response = unauthed_client.post(
            f"/v1/tool/test-tool-1/deployment?token={token}"
        )
        assert response.status_code == status.HTTP_200_OK

        expected_deployment = ToolDeploymentResponse.model_validate(response.json())
        expected_deployment.data.status = DeploymentState.successful
        expected_deployment.data.long_status = ANY
        expected_deployment.data.builds[
            "component1"
        ].build_status = DeploymentBuildState.successful
        expected_deployment.data.builds[
            "component1"
        ].build_id = DeploymentBuildInfo.NO_BUILD_NEEDED
        expected_deployment.data.runs[
            "component1"
        ].run_status = DeploymentRunState.successful
        expected_deployment.data.runs["component1"].run_long_status = ANY

        response = authenticated_client.get(
            f"/v1/tool/test-tool-1/deployment/{expected_deployment.data.deploy_id}"
        )

        assert response.status_code == status.HTTP_200_OK
        gotten_deployment = ToolDeploymentResponse.model_validate(response.json())
        # we kinda ignore the messages
        assert expected_deployment.data == gotten_deployment.data

        fake_toolforge_client.patch.assert_called_once_with(
            "/jobs/v1/tool/test-tool-1/jobs/",
            json={
                "cmd": "some command",
                "continuous": True,
                "name": "component1",
                "imagename": "tool-test-tool-1/silly_image:latest",
            },
            verify=True,
        )

    def test_creates_and_returns_the_new_deployment_of_source_build_job(
        self, authenticated_client: TestClient, fake_toolforge_client: MagicMock
    ):
        fake_toolforge_client.post.return_value = {
            "new_build": {"name": "new-build-id"}
        }
        fake_toolforge_client.get.return_value = {
            "build": {"status": BuildsBuildStatus.BUILD_SUCCESS.value}
        }
        fake_toolforge_client.patch.return_value = JobsJobResponse(
            job=get_defined_job(), messages=None
        ).model_dump()
        my_tool_config = get_fake_tool_config(
            build={"repository": "some_repo", "ref": "some_ref"}
        )
        response = authenticated_client.post(
            "/v1/tool/test-tool-1/config", content=my_tool_config.model_dump_json()
        )
        response.raise_for_status()

        response = authenticated_client.post("/v1/tool/test-tool-1/deployment")
        response.raise_for_status()

        expected_deployment = ToolDeploymentResponse.model_validate(response.json())
        expected_deployment.data.status = DeploymentState.successful
        expected_deployment.data.long_status = ANY
        expected_deployment.data.builds[
            "component1"
        ].build_status = DeploymentBuildState.successful
        expected_deployment.data.builds["component1"].build_id = "new-build-id"
        expected_deployment.data.runs[
            "component1"
        ].run_status = DeploymentRunState.successful
        expected_deployment.data.runs["component1"].run_long_status = ANY

        response = authenticated_client.get(
            f"/v1/tool/test-tool-1/deployment/{expected_deployment.data.deploy_id}"
        )

        assert response.status_code == status.HTTP_200_OK
        gotten_deployment = ToolDeploymentResponse.model_validate(response.json())
        # we kinda ignore the messages
        assert expected_deployment.data == gotten_deployment.data

        fake_toolforge_client.patch.assert_called_once_with(
            "/jobs/v1/tool/test-tool-1/jobs/",
            json={
                "cmd": "some command",
                "continuous": True,
                "name": "component1",
                "imagename": "tool-test-tool-1/component1:latest",
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

    def test_returns_conflict_when_trying_to_run_many_deployments_in_parallel(
        self,
        authenticated_client: TestClient,
        fake_toolforge_client: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ):
        settings = get_settings()
        fake_toolforge_client.post.return_value = {
            "new_build": {"name": "new-build-id"}
        }
        fake_toolforge_client.get.return_value = {"build": {"status": "BUILD_RUNNING"}}
        my_tool_config = get_fake_tool_config(
            build={"repository": "some_repo", "ref": "some_ref"}
        )
        response = authenticated_client.post(
            "/v1/tool/test-tool-1/config", content=my_tool_config.model_dump_json()
        )
        # as the deployment will never be ending, and during tests there's no real background tasks, we mock it so it
        # returns keeping the deployment pending
        monkeypatch.setattr(BackgroundTasks, "add_task", MagicMock())
        response.raise_for_status()
        for _ in range(settings.max_parallel_deployments):
            response = authenticated_client.post("/v1/tool/test-tool-1/deployment")
            response.raise_for_status()

        # one more should break
        response = authenticated_client.post("/v1/tool/test-tool-1/deployment")

        assert response.status_code == status.HTTP_409_CONFLICT


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

    def test_fails_when_token_already_exists(self, authenticated_client: TestClient):
        create_deploy_token(authenticated_client)
        second_response = authenticated_client.post(
            "/v1/tool/test-tool-1/deployment/token"
        )
        assert second_response.status_code == status.HTTP_409_CONFLICT
        delete_deploy_token(authenticated_client)

    def test_returns_500_on_any_other_exception(
        self, authenticated_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        def mock_get_deploy_token(self, tool_name: str):
            raise Exception("generic exception")

        monkeypatch.setattr(MockStorage, "get_deploy_token", mock_get_deploy_token)

        raw_response = authenticated_client.post(
            "/v1/tool/test-tool-1/deployment/token"
        )

        assert raw_response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_creates_new_token(self, authenticated_client: TestClient):
        create_response = create_deploy_token(authenticated_client)
        get_response = get_deploy_token(authenticated_client)
        assert create_response.data.token == get_response.data.token
        assert isinstance(create_response.data.token, UUID)
        delete_deploy_token(authenticated_client)


class TestUpdateDeployToken:
    def test_fails_without_auth_header(self, test_client: TestClient):
        raw_response = test_client.put("/v1/tool/test-tool-1/deployment/token")
        assert raw_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_fails_when_no_token_exists(self, authenticated_client: TestClient):
        delete_deploy_token(authenticated_client)
        raw_response = authenticated_client.put("/v1/tool/test-tool-1/deployment/token")
        assert raw_response.status_code == status.HTTP_404_NOT_FOUND

    def test_updates_existing_token(self, authenticated_client: TestClient):
        original_token = create_deploy_token(authenticated_client)
        update_response = authenticated_client.put(
            "/v1/tool/test-tool-1/deployment/token"
        )
        assert update_response.status_code == status.HTTP_200_OK
        update_data = DeployTokenResponse.model_validate(update_response.json())

        assert isinstance(update_data.data.token, UUID)
        assert update_data.data.token != original_token.data.token

        get_data = get_deploy_token(authenticated_client)
        assert get_data.data.token == update_data.data.token

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
        fake_toolforge_client.patch.return_value = JobsJobResponse(
            job=get_defined_job(), messages=None
        ).model_dump()
        deployment_response = create_tool_deployment(authenticated_client)
        expected_deployment = deployment_response.data
        expected_deployment.status = DeploymentState.successful
        expected_deployment.long_status = ANY
        expected_deployment.builds[
            "component1"
        ].build_status = DeploymentBuildState.successful
        expected_deployment.builds[
            "component1"
        ].build_id = DeploymentBuildInfo.NO_BUILD_NEEDED
        expected_deployment.runs[
            "component1"
        ].run_status = DeploymentRunState.successful
        expected_deployment.runs["component1"].run_long_status = ANY

        response = authenticated_client.get("/v1/tool/test-tool-1/deployment")
        assert response.status_code == status.HTTP_200_OK

        gotten_deployments = response.json()
        assert "data" in gotten_deployments
        assert "deployments" in gotten_deployments["data"]
        assert len(gotten_deployments["data"]["deployments"]) == 1
        assert (
            Deployment.model_validate(gotten_deployments["data"]["deployments"][0])
            == expected_deployment
        )

    def test_returns_multiple_deployments_when_they_exist(
        self, authenticated_client: TestClient, fake_toolforge_client: MagicMock
    ):
        create_tool_config(authenticated_client)
        first_deployment = create_tool_deployment(authenticated_client)
        second_deployment = create_tool_deployment(authenticated_client)

        response = authenticated_client.get("/v1/tool/test-tool-1/deployment")
        assert response.status_code == status.HTTP_200_OK

        deployments = response.json()
        assert "data" in deployments
        assert "deployments" in deployments["data"]
        assert len(deployments["data"]["deployments"]) == 2
        deployment_ids = {
            dep["deploy_id"] for dep in deployments["data"]["deployments"]
        }
        assert deployment_ids == {
            first_deployment.data.deploy_id,
            second_deployment.data.deploy_id,
        }


class TestBuildComponents:
    def test_builds_nothing_when_no_source_build_components(
        self, authenticated_client: TestClient, fake_toolforge_client: MagicMock
    ):
        my_tool_config = get_fake_tool_config(
            build={"use_prebuilt": "silly_prebuilt_image"},
        )
        response = authenticated_client.post(
            "/v1/tool/test-tool-1/config", content=my_tool_config.model_dump_json()
        )
        response.raise_for_status()

        fake_toolforge_client.patch.return_value = JobsJobResponse(
            job=get_defined_job(), messages=None
        ).model_dump()
        response = authenticated_client.post("/v1/tool/test-tool-1/deployment")
        response.raise_for_status()

        expected_deployment = ToolDeploymentResponse.model_validate(response.json())
        expected_deployment.data.status = DeploymentState.successful
        expected_deployment.data.long_status = ANY
        expected_deployment.data.builds[
            "component1"
        ].build_status = DeploymentBuildState.successful
        expected_deployment.data.builds[
            "component1"
        ].build_id = DeploymentBuildInfo.NO_BUILD_NEEDED
        expected_deployment.data.runs[
            "component1"
        ].run_status = DeploymentRunState.successful
        expected_deployment.data.runs["component1"].run_long_status = ANY

        response = authenticated_client.get(
            f"/v1/tool/test-tool-1/deployment/{expected_deployment.data.deploy_id}"
        )

        assert response.status_code == status.HTTP_200_OK
        gotten_deployment = ToolDeploymentResponse.model_validate(response.json())
        # we kinda ignore the messages
        assert expected_deployment.data == gotten_deployment.data

        fake_toolforge_client.patch.assert_called_once_with(
            "/jobs/v1/tool/test-tool-1/jobs/",
            json={
                "cmd": "some command",
                "continuous": True,
                "name": "component1",
                "imagename": "tool-test-tool-1/silly_prebuilt_image:latest",
            },
            verify=True,
        )

    def test_builds_one_component_when_its_source_build(
        self, authenticated_client: TestClient, fake_toolforge_client: MagicMock
    ):
        fake_toolforge_client.post.return_value = {
            "new_build": {"name": "new-build-id"}
        }
        fake_toolforge_client.get.return_value = {"build": {"status": "BUILD_SUCCESS"}}
        my_tool_config = get_fake_tool_config(
            build={"repository": "some_repo", "ref": "some_ref"}
        )
        response = authenticated_client.post(
            "/v1/tool/test-tool-1/config", content=my_tool_config.model_dump_json()
        )
        response.raise_for_status()

        fake_toolforge_client.patch.return_value = JobsJobResponse(
            job=get_defined_job(), messages=None
        ).model_dump()
        response = authenticated_client.post("/v1/tool/test-tool-1/deployment")
        response.raise_for_status()

        expected_deployment = ToolDeploymentResponse.model_validate(response.json())
        expected_deployment.data.status = DeploymentState.successful
        expected_deployment.data.long_status = ANY
        expected_deployment.data.builds[
            "component1"
        ].build_status = DeploymentBuildState.successful
        expected_deployment.data.builds["component1"].build_id = "new-build-id"
        expected_deployment.data.runs[
            "component1"
        ].run_status = DeploymentRunState.successful
        expected_deployment.data.runs["component1"].run_long_status = ANY

        response = authenticated_client.get(
            f"/v1/tool/test-tool-1/deployment/{expected_deployment.data.deploy_id}"
        )

        assert response.status_code == status.HTTP_200_OK
        gotten_deployment = ToolDeploymentResponse.model_validate(response.json())
        # we kinda ignore the messages
        assert expected_deployment.data == gotten_deployment.data

        fake_toolforge_client.patch.assert_called_once_with(
            "/jobs/v1/tool/test-tool-1/jobs/",
            json={
                "cmd": "some command",
                "continuous": True,
                "name": "component1",
                "imagename": "tool-test-tool-1/component1:latest",
            },
            verify=True,
        )
