import http

import pytest
from fastapi.testclient import TestClient

from components.main import create_app
from components.models.api_models import Message, ToolConfig, ToolConfigResponse


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


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


def test_healthz_endpoint(client: TestClient):
    """
    Test the /healthz endpoint to ensure it returns the correct status.
    """
    response = client.get("/v1/healthz")
    assert (
        response.status_code == http.HTTPStatus.OK
    ), f"Unexpected status code: {response.status_code}"
    assert response.json() == {
        "status": "ok"
    }, f"Unexpected response content: {response.json()}"


def test_update_tool_config_sets_when_valid_config(client: TestClient):
    expected_tool_config = get_tool_config()
    raw_response = client.post(
        "/v1/tool/test-tool-1/config", content=expected_tool_config.model_dump_json()
    )

    assert raw_response.status_code == http.HTTPStatus.OK
    gotten_response = ToolConfigResponse.model_validate(raw_response.json())
    assert gotten_response.data == expected_tool_config
    assert gotten_response.messages != []


def test_update_tool_config_fails_when_invalid_config_sent(client: TestClient):
    raw_response = client.post("/v1/tool/test-tool-1/config", content="")

    assert raw_response.status_code == http.HTTPStatus.UNPROCESSABLE_ENTITY


def test_get_tool_config_returns_not_found_when_tool_does_not_exist(client: TestClient):
    raw_response = client.get("/v1/tool/idontexist/config")

    assert raw_response.status_code == http.HTTPStatus.NOT_FOUND


def test_get_tool_config_retrieves_the_set_config_happy_path(client: TestClient):
    my_tool_config = get_tool_config()
    expected_response = ToolConfigResponse(
        messages=Message(),
        data=my_tool_config,
    )
    response = client.post(
        "/v1/tool/test-tool-1/config", content=my_tool_config.model_dump_json()
    )
    response.raise_for_status()

    response = client.get("/v1/tool/test-tool-1/config")

    assert response.status_code == http.HTTPStatus.OK
    gotten_response = ToolConfigResponse.model_validate(response.json())
    assert gotten_response == expected_response
