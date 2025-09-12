import json
from unittest.mock import ANY, MagicMock
from uuid import UUID

import pytest
import requests
import yaml
from fastapi import BackgroundTasks, FastAPI, status
from fastapi.testclient import TestClient

from components.gen.toolforge_models import (
    BuildsBuild,
    BuildsBuildParameters,
    BuildsBuildStatus,
    JobsHttpHealthCheck,
    JobsJobResponse,
    JobsScriptHealthCheck,
)
from components.models.api_models import (
    EXAMPLE_GENERATED_CONFIG,
    ContinuousComponentInfo,
    ContinuousRunInfo,
    Deployment,
    DeploymentBuildInfo,
    DeploymentBuildState,
    DeploymentRunInfo,
    DeploymentRunState,
    DeploymentState,
    DeployTokenResponse,
    HealthState,
    HealthzResponse,
    ResponseMessages,
    SourceBuildInfo,
    ToolConfig,
    ToolConfigResponse,
    ToolDeploymentResponse,
)
from components.runtime.utils import get_runtime
from components.settings import get_settings
from components.storage.mock import MockStorage
from components.storage.utils import get_storage
from tests.helpers import (
    create_deploy_token,
    create_tool_config,
    create_tool_deployment,
    delete_deploy_token,
    delete_tool_config,
    get_deploy_token,
    get_fake_tool_config,
)
from tests.testlibs import get_defined_job, get_tool_config


def test_healthz_endpoint_returns_ok_status(test_client: TestClient):
    expected_state = HealthState(status="OK")

    raw_response = test_client.get("/v1/healthz")

    assert raw_response.status_code == status.HTTP_200_OK
    gotten_state = HealthzResponse.model_validate(raw_response.json()).data
    assert gotten_state == expected_state


class TestUpdateToolConfig:
    def test_succeeds_with_valid_config(self, authenticated_client: TestClient):
        expected_tool_config = get_fake_tool_config()
        expected_messages = ResponseMessages(
            warning=["You are using a beta feature of Toolforge."],
            info=["Configuration for test-tool-1 updated successfully."],
        )
        raw_response = authenticated_client.post(
            "/v1/tool/test-tool-1/config",
            content=expected_tool_config.model_dump_json(),
        )

        assert raw_response.status_code == status.HTTP_200_OK
        gotten_response = ToolConfigResponse.model_validate(raw_response.json())
        assert gotten_response.data == expected_tool_config
        assert gotten_response.messages == expected_messages

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

    def test_returns_warning_with_unknown_fields(
        self, authenticated_client: TestClient
    ):
        expected_tool_config = get_fake_tool_config()
        expected_messages = ResponseMessages(
            warning=[
                "You are using a beta feature of Toolforge.",
                "Unknown field components.component1.internal_extra_field, skipped",
                "Unknown field extra_field_1, skipped",
            ],
            info=["Configuration for test-tool-1 updated successfully."],
        )
        sent_config = json.loads(expected_tool_config.model_dump_json())
        sent_config["extra_field_1"] = 1234
        sent_config["components"]["component1"]["internal_extra_field"] = 1234
        raw_response = authenticated_client.post(
            "/v1/tool/test-tool-1/config", json=sent_config
        )

        assert raw_response.status_code == status.HTTP_200_OK
        gotten_response = ToolConfigResponse.model_validate(raw_response.json())
        assert gotten_response.data == expected_tool_config
        assert gotten_response.messages == expected_messages

    def test_fetches_config_when_source_url_passed(
        self, authenticated_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        expected_tool_config = get_fake_tool_config(
            source_url="http://idontexist.local/myconfig"
        )

        expected_messages = ResponseMessages(
            warning=[
                "You are using a beta feature of Toolforge.",
            ],
            info=["Configuration for test-tool-1 updated successfully."],
        )
        sent_config_json = json.loads(expected_tool_config.model_dump_json())

        response_mock = MagicMock()
        response_mock.text = yaml.safe_dump(
            json.loads(expected_tool_config.model_dump_json())
        )
        get_mock = MagicMock()
        get_mock.return_value = response_mock
        monkeypatch.setattr(requests, "get", get_mock)

        raw_response = authenticated_client.post(
            "/v1/tool/test-tool-1/config", json=sent_config_json
        )

        assert raw_response.status_code == status.HTTP_200_OK
        gotten_response = ToolConfigResponse.model_validate(raw_response.json())
        assert gotten_response.data == expected_tool_config
        assert gotten_response.messages == expected_messages
        get_mock.assert_called_once()

    def test_fails_with_missing_referenced_component(
        self, authenticated_client: TestClient
    ):
        config_json = {
            "components": {
                "my-component": {
                    "build": {
                        "ref": "main",
                        "repository": "https://gitlab-example.wikimedia.org/my-repo.git",
                        "use_latest_versions": False,
                    },
                    "component_type": "continuous",
                    "run": {"command": "my-command"},
                },
                "child-component": {
                    "build": {"reuse_from": "very-important"},
                    "component_type": "continuous",
                    "run": {"command": "child-command"},
                },
            },
            "config_version": "v1beta1",
        }
        raw_response = authenticated_client.post(
            "/v1/tool/test-tool-1/config", json=config_json
        )
        assert raw_response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert (
            "Missing components referenced from reuse_from: very-important"
            in raw_response.json()["messages"]["error"][0]
        )

    def test_fails_with_non_authoritative_referenced_component(
        self, authenticated_client: TestClient
    ):
        config_json = {
            "components": {
                "parent-component": {
                    "build": {
                        "ref": "main",
                        "repository": "https://gitlab-example.wikimedia.org/some-repo.git",
                        "use_latest_versions": False,
                    },
                    "component_type": "continuous",
                    "run": {"command": "my-command"},
                },
                "child-component": {
                    "build": {"reuse_from": "parent-component"},
                    "component_type": "continuous",
                    "run": {"command": "child-command"},
                },
                "sub-child-component": {
                    "build": {"reuse_from": "child-component"},
                    "component_type": "continuous",
                    "run": {"command": "child-command"},
                },
            },
            "config_version": "v1beta1",
        }
        raw_response = authenticated_client.post(
            "/v1/tool/test-tool-1/config", json=config_json
        )
        assert raw_response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert (
            "The following components reuse builds from components that also use reuse_from. They should point to "
            "the original components instead: child-component"
        ) in raw_response.json()["messages"]["error"][0]


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

    def test_creates_and_returns_the_new_deployment_of_source_built_component_using_header_auth(
        self, authenticated_client: TestClient, fake_toolforge_client: MagicMock
    ):
        create_tool_config(authenticated_client)
        fake_toolforge_client.post.return_value = {
            "new_build": {"name": "new-build-id"}
        }
        fake_toolforge_client.get.return_value = {
            "build": {"status": BuildsBuildStatus.BUILD_SUCCESS.value}
        }
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
        expected_deployment.data.builds["component1"].build_id = "new-build-id"
        expected_deployment.data.builds[
            "component1"
        ].build_long_status = (
            "You can see the logs with `toolforge build logs new-build-id`"
        )
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
                "cpu": "0.5",
                "filelog": False,
                "health_check": {"path": "/health", "type": "http"},
                "imagename": "tool-test-tool-1/component1:latest",
                "memory": "256Mi",
                "mount": "none",
                "name": "component1",
                "port": 8080,
                "replicas": 2,
            },
            verify=True,
        )

    @pytest.mark.asyncio
    async def test_creates_and_returns_the_new_deployment_of_source_built_component_using_token(
        self,
        authenticated_client: TestClient,
        fake_toolforge_client: MagicMock,
        app: FastAPI,
    ):
        create_tool_config(authenticated_client)
        token_response = create_deploy_token(authenticated_client)
        token = str(token_response.data.token)
        fake_toolforge_client.post.return_value = {
            "new_build": {"name": "new-build-id"}
        }
        fake_toolforge_client.get.return_value = {
            "build": {"status": BuildsBuildStatus.BUILD_SUCCESS.value}
        }
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
        expected_deployment.data.builds["component1"].build_id = "new-build-id"
        expected_deployment.data.builds[
            "component1"
        ].build_long_status = (
            "You can see the logs with `toolforge build logs new-build-id`"
        )
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
                "cpu": "0.5",
                "filelog": False,
                "health_check": {"path": "/health", "type": "http"},
                "imagename": "tool-test-tool-1/component1:latest",
                "memory": "256Mi",
                "mount": "none",
                "name": "component1",
                "port": 8080,
                "replicas": 2,
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
            build={
                "repository": "https://gitlab-example.wikimedia.org/some-repo.git",
                "ref": "some_ref",
            }
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
        expected_deployment.data.builds[
            "component1"
        ].build_long_status = (
            "You can see the logs with `toolforge build logs new-build-id`"
        )
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
                "cpu": "0.5",
                "filelog": False,
                "health_check": {"path": "/health", "type": "http"},
                "imagename": "tool-test-tool-1/component1:latest",
                "memory": "256Mi",
                "mount": "none",
                "name": "component1",
                "port": 8080,
                "replicas": 2,
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

    def test_returns_conflict_when_trying_to_create_many_active_deployments(
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
            build={
                "repository": "https://gitlab-example.wikimedia.org/some-repo.git",
                "ref": "some_ref",
            }
        )
        response = authenticated_client.post(
            "/v1/tool/test-tool-1/config", content=my_tool_config.model_dump_json()
        )
        # as the deployment will never be ending, and during tests there's no real background tasks, we mock it so it
        # returns keeping the deployment pending
        monkeypatch.setattr(BackgroundTasks, "add_task", MagicMock())
        response.raise_for_status()
        for _ in range(settings.max_active_deployments):
            response = authenticated_client.post("/v1/tool/test-tool-1/deployment")
            response.raise_for_status()

        # one more should break
        response = authenticated_client.post("/v1/tool/test-tool-1/deployment")

        assert response.status_code == status.HTTP_409_CONFLICT

    def test_fetches_config_when_source_url_passed(
        self,
        authenticated_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        fake_toolforge_client: MagicMock,
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
            source_url="http://idontexist.local/myconfig",
            build={
                "repository": "https://gitlab-example.wikimedia.org/some-repo.git",
                "ref": "some_ref",
            },
        )
        response_mock = MagicMock()
        response_mock.text = yaml.safe_dump(
            json.loads(my_tool_config.model_dump_json())
        )
        get_mock = MagicMock()
        get_mock.return_value = response_mock
        monkeypatch.setattr(requests, "get", get_mock)
        response = authenticated_client.post(
            "/v1/tool/test-tool-1/config", content=my_tool_config.model_dump_json()
        )
        response.raise_for_status()
        get_mock.assert_called_once()
        get_mock.reset_mock()

        response = authenticated_client.post("/v1/tool/test-tool-1/deployment")
        response.raise_for_status()

        get_mock.assert_called_once()


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
        fake_toolforge_client.post.return_value = {
            "new_build": {"name": "new-build-id"}
        }
        fake_toolforge_client.get.return_value = {
            "build": {"status": BuildsBuildStatus.BUILD_SUCCESS.value}
        }
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
        expected_deployment.builds["component1"].build_id = "new-build-id"
        expected_deployment.builds[
            "component1"
        ].build_long_status = (
            "You can see the logs with `toolforge build logs new-build-id`"
        )
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

    def test_returns_one_deployment_when_there_are_multiple_deployments(
        self, authenticated_client: TestClient, fake_toolforge_client: MagicMock
    ):
        create_tool_config(authenticated_client)
        first_deployment = create_tool_deployment(authenticated_client)
        response = authenticated_client.get("/v1/tool/test-tool-1/deployment/latest")
        assert response.status_code == status.HTTP_200_OK

        latest_deployment = response.json()
        assert "data" in latest_deployment
        assert latest_deployment["data"]["deploy_id"] == first_deployment.data.deploy_id

        second_deployment = create_tool_deployment(authenticated_client)

        response = authenticated_client.get("/v1/tool/test-tool-1/deployment/latest")
        assert response.status_code == status.HTTP_200_OK

        latest_deployment = response.json()
        assert "data" in latest_deployment
        assert (
            latest_deployment["data"]["deploy_id"] == second_deployment.data.deploy_id
        )


class TestBuildComponents:
    def test_builds_one_component_when_its_source_build(
        self, authenticated_client: TestClient, fake_toolforge_client: MagicMock
    ):
        fake_toolforge_client.post.return_value = {
            "new_build": {"name": "new-build-id"}
        }
        fake_toolforge_client.get.return_value = {"build": {"status": "BUILD_SUCCESS"}}
        my_tool_config = get_fake_tool_config(
            build={
                "repository": "https://gitlab-example.wikimedia.org/some-repo.git",
                "ref": "some_ref",
            }
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
        expected_deployment.data.builds[
            "component1"
        ].build_long_status = (
            "You can see the logs with `toolforge build logs new-build-id`"
        )
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
                "cpu": "0.5",
                "filelog": False,
                "health_check": {"path": "/health", "type": "http"},
                "imagename": "tool-test-tool-1/component1:latest",
                "memory": "256Mi",
                "mount": "none",
                "name": "component1",
                "port": 8080,
                "replicas": 2,
            },
            verify=True,
        )


class TestGenerateConfig:
    def test_generates_for_two_continuous_jobs(
        self, authenticated_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        runtime = get_runtime(settings=get_settings())
        jobs = [
            get_defined_job(
                name="job1",
                health_check=JobsScriptHealthCheck(
                    script="test -e /tmp/everything_ok", type="script"
                ),
                image="job1-image",
            ),
            get_defined_job(
                name="job2",
                health_check=JobsHttpHealthCheck(path="/healthz", type="http"),
                port=1234,
                image="job2-image",
            ),
        ]
        monkeypatch.setattr(
            target=runtime, name="get_jobs", value=lambda *args, **kwargs: jobs
        )
        builds = [
            BuildsBuild(
                destination_image=jobs[0].image,
                parameters=BuildsBuildParameters(
                    source_url="https://some.source/url", ref="some-ref"
                ),
            ),
            BuildsBuild(
                destination_image=jobs[1].image,
                parameters=BuildsBuildParameters(source_url="https://some.source/url"),
            ),
        ]
        monkeypatch.setattr(
            target=runtime, name="get_builds", value=lambda *args, **kwargs: builds
        )

        expected_config = ToolConfigResponse(
            data=ToolConfig(
                components={
                    "job1": ContinuousComponentInfo(
                        build=SourceBuildInfo(
                            repository="https://some.source/url",
                            ref="some-ref",
                        ),
                        run=ContinuousRunInfo(
                            command=jobs[0].cmd,
                            health_check_script="test -e /tmp/everything_ok",
                        ),
                    ),
                    "job2": ContinuousComponentInfo(
                        component_type="continuous",
                        build=SourceBuildInfo(
                            repository="https://some.source/url", ref="HEAD"
                        ),
                        run=ContinuousRunInfo(
                            command=jobs[0].cmd, health_check_http="/healthz", port=1234
                        ),
                    ),
                }
            ),
            messages=ResponseMessages(
                info=[],
                warning=[
                    "Note that this config is an autogenerated example, please double check and validate before using it"
                ],
                error=[],
            ),
        )

        raw_response = authenticated_client.get("/v1/tool/test-tool-1/config/generate")
        parsed_response = ToolConfigResponse.model_validate(raw_response.json())

        assert parsed_response.data == expected_config.data
        assert parsed_response.messages == expected_config.messages

    def test_generates_example_if_no_supported_jobs(
        self, authenticated_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        runtime = get_runtime(settings=get_settings())
        jobs = [
            get_defined_job(
                name="job1",
                image="i-have-no-matching-build",
            ),
            get_defined_job(
                name="job2",
                continuous=False,
            ),
        ]
        monkeypatch.setattr(
            target=runtime, name="get_jobs", value=lambda *args, **kwargs: jobs
        )
        monkeypatch.setattr(
            target=runtime, name="get_builds", value=lambda *args, **kwargs: []
        )

        expected_config = ToolConfigResponse(
            data=EXAMPLE_GENERATED_CONFIG,
            messages=ResponseMessages(
                info=[],
                warning=[
                    "Note that this config is an autogenerated example, please double check and validate before using it",
                    "Job job1 seems not to be a build-service based job (or no build found for it), skipping",
                    "Job job2 seems not to be a build-service based job (or no build found for it), skipping",
                    "No components were able to be generated from your tool, a sample set of them is returned instead",
                ],
                error=[],
            ),
        )

        raw_response = authenticated_client.get("/v1/tool/test-tool-1/config/generate")
        parsed_response = ToolConfigResponse.model_validate(raw_response.json())

        assert parsed_response.data == expected_config.data
        assert parsed_response.messages == expected_config.messages


class TestCancelDeployment:
    def test_fails_without_auth_header(self, test_client: TestClient):
        raw_response = test_client.put("/v1/tool/test-tool-1/deployment/some-id/cancel")

        assert raw_response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_fails_if_tool_has_no_config(self, authenticated_client: TestClient):
        authenticated_client.delete("/v1/tool/test-tool-1/config")
        raw_response = authenticated_client.get("/v1/tool/test-tool-1/config")
        assert raw_response.status_code == status.HTTP_404_NOT_FOUND

        raw_response = authenticated_client.put(
            "/v1/tool/test-tool-1/deployment/some-id/cancel"
        )

        assert raw_response.status_code == status.HTTP_404_NOT_FOUND

    def test_returns_not_found_when_tool_does_not_exist(
        self,
        authenticated_client: TestClient,
    ):
        raw_response = authenticated_client.put(
            "/v1/tool/idontexist/deployment/some-id/cancel"
        )

        assert raw_response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.parametrize(
        "deployment_status", [DeploymentState.pending, DeploymentState.running]
    )
    def test_flags_deployment_for_cancellation(
        self, authenticated_client: TestClient, deployment_status: DeploymentState
    ):
        create_tool_config(authenticated_client)

        # this breaks a bit the barrier between api tests only testing through the api, but found no nicer way to
        # test this as we have to catch the deployment "on the fly"
        storage = get_storage()
        storage.create_deployment(
            tool_name="test-tool-1",
            deployment=Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.pending,
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.pending,
                        run_long_status="",
                    )
                },
                tool_config=get_tool_config(),
                status=deployment_status,
                long_status="",
            ),
        )

        response = authenticated_client.put(
            "/v1/tool/test-tool-1/deployment/my-deploy-id/cancel"
        )
        assert response.status_code == status.HTTP_200_OK

        expected_deployment = ToolDeploymentResponse.model_validate(response.json())
        expected_deployment.data.status = DeploymentState.cancelling

    @pytest.mark.parametrize(
        "deployment_status",
        [
            DeploymentState.cancelled,
            DeploymentState.cancelling,
            DeploymentState.failed,
            DeploymentState.successful,
            DeploymentState.timed_out,
        ],
    )
    def test_deployment_cancel_returns_conflict_if_deployment_not_running(
        self, authenticated_client: TestClient, deployment_status: DeploymentState
    ):
        create_tool_config(authenticated_client)

        # this breaks a bit the barrier between api tests only testing through the api, but found no nicer way to
        # test this as we have to catch the deployment "on the fly"
        storage = get_storage()
        storage.create_deployment(
            tool_name="test-tool-1",
            deployment=Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.pending,
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.pending,
                        run_long_status="",
                    )
                },
                tool_config=get_tool_config(),
                status=deployment_status,
                long_status="",
            ),
        )

        response = authenticated_client.put(
            "/v1/tool/test-tool-1/deployment/my-deploy-id/cancel"
        )
        assert response.status_code == status.HTTP_409_CONFLICT
