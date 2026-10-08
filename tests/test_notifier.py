import json
from unittest.mock import create_autospec

import pytest
from toolforge_weld.api_client import ToolforgeClient

import components.notifier
from components.models.api_models import (
    Deployment,
    DeploymentBuildInfo,
    DeploymentBuildState,
)
from components.notifier import DeploymentCreated, DeploymentFailed, notify

from .testlibs import get_deployment_from_tool_config, get_tool_config


def get_deployment() -> Deployment:
    deployment = get_deployment_from_tool_config(
        tool_config=get_tool_config(), description="my description"
    )
    deployment.builds["skipped-component"] = DeploymentBuildInfo(
        build_id=DeploymentBuildInfo.NO_BUILD_NEEDED,
        build_status=DeploymentBuildState.skipped,
    )
    return deployment


def test_from_deployment_gets_common_fields_and_skips_non_build_ids():
    event = DeploymentCreated.from_deployment(
        deployment=get_deployment(), user_name="me"
    )

    assert event.model_dump(exclude={"datetime"}) == {
        "source": "deployments",
        "event_type": "created",
        "deployment_id": "my-deploy-id",
        "user_name": "me",
        "jobs": ["my-component"],
        "builds": ["my-build-id"],
        "description": "my description",
    }


def test_failed_message_is_json_error():
    deployment = get_deployment()
    event = DeploymentFailed.from_failed_deployment(
        deployment=deployment, user_name="me"
    )
    assert json.loads(event.message) == {"error": deployment.long_status}


def test_notify_posts_to_logs_api(monkeypatch: pytest.MonkeyPatch):
    client = create_autospec(ToolforgeClient, spec_set=True, instance=True)
    monkeypatch.setattr(components.notifier, "get_toolforge_client", lambda: client)
    event = DeploymentCreated(deployment_id="my-deploy-id")

    notify(tool_name="my-tool", event=event)

    client.post.assert_called_once()
    assert client.post.call_args.kwargs["url"] == (
        "/logs/v1/tool/my-tool/source/deployments/log"
    )
    assert client.post.call_args.kwargs["json"] == [event.model_dump(mode="json")]


def test_notify_does_not_raise(monkeypatch: pytest.MonkeyPatch):
    client = create_autospec(ToolforgeClient, spec_set=True, instance=True)
    client.post.side_effect = Exception("logs-api is down")
    monkeypatch.setattr(components.notifier, "get_toolforge_client", lambda: client)

    notify(tool_name="my-tool", event=DeploymentCreated(deployment_id="my-deploy-id"))
