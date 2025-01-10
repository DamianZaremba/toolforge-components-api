from fastapi import status
from fastapi.testclient import TestClient

from components.models.api_models import (
    DeployTokenResponse,
    ToolConfig,
    ToolConfigResponse,
    ToolDeploymentResponse,
)


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


def create_tool_config(
    client: TestClient, tool_name: str = "test-tool-1"
) -> ToolConfigResponse:
    tool_config = get_fake_tool_config()
    response = client.post(
        f"/v1/tool/{tool_name}/config", content=tool_config.model_dump_json()
    )
    assert response.status_code == status.HTTP_200_OK
    return ToolConfigResponse.model_validate(response.json())


def delete_tool_config(
    client: TestClient, tool_name: str = "test-tool-1"
) -> ToolConfigResponse:
    response = client.delete(f"/v1/tool/{tool_name}/config")
    assert response.status_code == status.HTTP_200_OK
    return ToolConfigResponse.model_validate(response.json())


def create_deploy_token(
    client: TestClient, tool_name: str = "test-tool-1"
) -> DeployTokenResponse:
    delete_deploy_token(client, tool_name)

    response = client.post(f"/v1/tool/{tool_name}/deployment/token")
    assert response.status_code == status.HTTP_200_OK
    return DeployTokenResponse.model_validate(response.json())


def delete_deploy_token(
    client: TestClient, tool_name: str = "test-tool-1"
) -> DeployTokenResponse:
    response = client.delete(f"/v1/tool/{tool_name}/deployment/token")
    assert response.status_code in (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND)
    if response.status_code == status.HTTP_200_OK:
        return DeployTokenResponse.model_validate(response.json())
    return None


def get_deploy_token(
    client: TestClient, tool_name: str = "test-tool-1"
) -> DeployTokenResponse:
    response = client.get(f"/v1/tool/{tool_name}/deployment/token")
    return DeployTokenResponse.model_validate(response.json())


def create_tool_deployment(
    client: TestClient, tool_name: str = "test-tool-1"
) -> ToolDeploymentResponse:
    response = client.post(f"/v1/tool/{tool_name}/deployment")
    assert response.status_code == status.HTTP_200_OK
    return ToolDeploymentResponse.model_validate(response.json())
