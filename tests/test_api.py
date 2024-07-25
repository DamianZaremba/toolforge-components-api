import pytest
from fastapi.testclient import TestClient

from components.api import create_app

client = TestClient(create_app())


def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"hello": "world"}


# dummy test to test tox/pytest setup
@pytest.mark.parametrize(
    "test_input,expected",
    [
        (4, 16),
        (0, 0),
        (-2, 4),
    ],
)
def test_dummy_square(test_input, expected):
    assert test_input**2 == expected
