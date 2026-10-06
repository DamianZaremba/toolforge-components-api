import json
from datetime import UTC, datetime
from functools import partial
from logging import getLogger
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, Field

from .client import get_toolforge_client
from .models.api_models import Deployment, DeploymentBuildInfo
from .settings import get_settings

logger = getLogger(__name__)

NOT_BUILD_IDS = (DeploymentBuildInfo.NO_ID_YET, DeploymentBuildInfo.NO_BUILD_NEEDED)


class DeploymentEvent(BaseModel):
    # These models are here rather than in components.models.api_models
    # because they aren’t part of components-api’s own API.
    source: Literal["deployments"] = "deployments"
    deployment_id: str
    datetime: AwareDatetime = Field(default_factory=partial(datetime.now, tz=UTC))
    user_name: str = ""
    jobs: list[str] = []
    builds: list[str] = []
    description: str = ""

    @classmethod
    def from_deployment(cls, deployment: Deployment, user_name: str) -> Self:
        return cls(
            deployment_id=deployment.deploy_id,
            user_name=user_name,
            jobs=list(deployment.runs),
            builds=[
                build.build_id
                for build in deployment.builds.values()
                if build.build_id not in NOT_BUILD_IDS
            ],
            description=deployment.description,
        )


class DeploymentCreated(DeploymentEvent):
    event_type: Literal["created"] = "created"


class DeploymentSucceeded(DeploymentEvent):
    event_type: Literal["succeeded"] = "succeeded"


class DeploymentFailed(DeploymentEvent):
    event_type: Literal["failed"] = "failed"
    message_format: Literal["json"] = "json"
    message: str = "{}"

    @classmethod
    def from_failed_deployment(cls, deployment: Deployment, user_name: str) -> Self:
        event = cls.from_deployment(deployment=deployment, user_name=user_name)
        event.message = json.dumps({"error": deployment.long_status})
        return event


def notify(tool_name: str, event: DeploymentEvent) -> None:
    """Sends the event to logs-api, never raises as it should not break deployments."""
    try:
        get_toolforge_client().post(
            url=f"/logs/v1/tool/{tool_name}/source/deployments/log",
            json=[event.model_dump(mode="json")],
            verify=get_settings().verify_toolforge_api_cert,
        )
    except Exception:
        logger.exception(f"Unable to send deployment event for {tool_name}: {event}")
