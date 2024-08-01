import pytest
from fastapi.testclient import TestClient

from components.api.tool_handlers import MOCK_DEPLOYMENTS, MOCK_TOOL_NAME
from components.main import API_PREFIX, create_app
from components.models.pydantic import Deployment

# Generic mock messages for testing
MOCK_MESSAGES = {
    "info": ["This is an example info message."],
    "warning": ["This is an example warning message."],
    "error": ["This is an example error message."],
}


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def reset_mock_data():
    MOCK_DEPLOYMENTS.clear()
    MOCK_DEPLOYMENTS["12345"] = Deployment(
        deploy_id="12345", toolname=MOCK_TOOL_NAME, status="in_progress"
    )


def test_get_tool_config(client):
    response = client.get(f"{API_PREFIX}/tool/{MOCK_TOOL_NAME}/config")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["data"] == {"config": "tf-test_config"}
    assert response_data["messages"]["info"] == []


def test_update_tool_config(client):
    response = client.post(
        f"{API_PREFIX}/tool/{MOCK_TOOL_NAME}/config", json={"config": {}}
    )
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["data"] == {
        "message": f"Configuration for {MOCK_TOOL_NAME} updated successfully"
    }
    assert response_data["messages"]["warning"] == []


def test_create_deployment(client):
    response = client.post(f"{API_PREFIX}/tool/{MOCK_TOOL_NAME}/deploy")
    assert response.status_code == 200
    response_data = response.json()
    assert "deploy_id" in response_data["data"]
    assert isinstance(response_data["data"]["deploy_id"], str)
    assert len(response_data["data"]["deploy_id"]) == 5
    assert response_data["data"]["status"] == "started"
    assert response_data["data"]["toolname"] == MOCK_TOOL_NAME
    assert response_data["messages"]["info"] == []


def test_get_deployment(client):
    response = client.get(f"{API_PREFIX}/tool/{MOCK_TOOL_NAME}/deploy/12345")
    assert response.status_code == 200
    response_data = response.json()
    assert response_data["data"] == {
        "deploy_id": "12345",
        "toolname": MOCK_TOOL_NAME,
        "status": "in_progress",
    }
    assert "messages" in response_data
    assert response_data["messages"] == {
        "info": [],
        "warning": [],
        "error": [],
    }
