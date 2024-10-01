import pytest
from fastapi.testclient import TestClient

from components.main import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_healthz_endpoint(client: TestClient):
    """
    Test the /healthz endpoint to ensure it returns the correct status.
    """
    response = client.get("/v1/healthz")
    assert (
        response.status_code == 200
    ), f"Unexpected status code: {response.status_code}"
    assert response.json() == {
        "status": "ok"
    }, f"Unexpected response content: {response.json()}"
