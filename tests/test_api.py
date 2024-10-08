import pytest
from fastapi import status
from fastapi.testclient import TestClient

from components.main import create_app
from components.models.api_models import (
    HealthState,
    HealthzResponse,
    ResponseMessages,
    ToolConfig,
    ToolConfigResponse,
)


@pytest.fixture
def test_client():
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def authenticated_client(test_client):
    test_client.headers.update({"x-toolforge-tool": "test-tool-1"})
    return test_client


def get_tool_config(**overrides) -> ToolConfig:
    params = {
        "config_version": "v1",
        "components": {
            "component1": {
                "build": {
                    "repository": "https://some.url.local/my-git-repo",
                },
                "component_type": "continuous",
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


def test_update_tool_config_succeeds_with_valid_config(
    authenticated_client: TestClient,
):
    expected_tool_config = get_tool_config()
    raw_response = authenticated_client.post(
        "/v1/tool/test-tool-1/config", content=expected_tool_config.model_dump_json()
    )

    assert raw_response.status_code == status.HTTP_200_OK
    gotten_response = ToolConfigResponse.model_validate(raw_response.json())
    assert gotten_response.data == expected_tool_config
    assert gotten_response.messages != []


def test_update_tool_config_fails_with_invalid_config_data(
    authenticated_client: TestClient,
):
    raw_response = authenticated_client.post("/v1/tool/test-tool-1/config", content="")

    assert raw_response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_update_tool_config_fails_without_auth_header(test_client: TestClient):
    expected_tool_config = get_tool_config()
    raw_response = test_client.post(
        "/v1/tool/test-tool-1/config", content=expected_tool_config.model_dump_json()
    )

    assert raw_response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_tool_config_returns_not_found_when_tool_does_not_exist(
    authenticated_client: TestClient,
):
    raw_response = authenticated_client.get("/v1/tool/idontexist/config")

    assert raw_response.status_code == status.HTTP_404_NOT_FOUND


def test_get_tool_config_retrieves_the_set_config(authenticated_client: TestClient):
    my_tool_config = get_tool_config()
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


def test_delete_tool_config_fails_when_config_does_not_exist(
    authenticated_client: TestClient,
):
    response = authenticated_client.delete("/v1/tool/nonexistent-tool/config")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    json_response = response.json()
    assert json_response["data"] is None
    assert (
        "No configuration found for tool: nonexistent-tool"
        in json_response["messages"]["error"]
    )


def test_delete_tool_config_succeeds_when_config_exists(
    authenticated_client: TestClient,
):
    my_tool_config = get_tool_config()
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
