import datetime
import random
import string
from typing import Generic, Literal, Type, TypeAlias, TypeVar
from uuid import UUID, uuid4

from pydantic import AnyUrl, BaseModel, Field

# TODO: add the others when we add support for them
ComponentType: TypeAlias = Literal["continuous"]
T = TypeVar("T")
# this comes from k8s name limitations, handy for us, but any is as god
DEPLOYMENT_NAME_MAX_LENGTH = 53


class BuildInfo(BaseModel):
    repository: AnyUrl
    ref: str | None = None


class ComponentInfo(BaseModel):
    component_type: ComponentType
    build: BuildInfo


class ToolConfig(BaseModel):
    config_version: str
    components: dict[str, ComponentInfo] = Field(..., min_length=1)


class ResponseMessages(BaseModel):
    info: list[str] = []
    warning: list[str] = []
    error: list[str] = []


class ApiResponse(BaseModel, Generic[T]):
    data: T
    messages: ResponseMessages = ResponseMessages()


class HealthState(BaseModel):
    status: Literal["OK", "ERROR"]


class DeploymentBuildInfo(BaseModel):
    build_id: str


class Deployment(BaseModel):
    deploy_id: str
    creation_time: str
    builds: dict[str, DeploymentBuildInfo]

    @classmethod
    def get_new_deployment(
        cls: "Type[Deployment]", tool_name: str, builds: dict[str, DeploymentBuildInfo]
    ) -> "Deployment":
        cur_timestamp = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%d-%H%M%S")
        # We rely on random having enough entropy and having little requests per second requests to not collide.
        random_suffix = "".join(
            random.choices(
                string.ascii_lowercase + string.digits, k=DEPLOYMENT_NAME_MAX_LENGTH
            )
        )
        new_id = f"{tool_name}-{cur_timestamp}-{random_suffix}"
        return Deployment(
            creation_time=cur_timestamp,
            deploy_id=new_id,
            builds=builds,
        )


class DeploymentToken(BaseModel):
    token: UUID = Field(default_factory=uuid4)


ToolConfigResponse = ApiResponse[ToolConfig]
HealthzResponse = ApiResponse[HealthState]
ToolDeploymentResponse = ApiResponse[Deployment]
DeploymentTokenResponse = ApiResponse[DeploymentToken]
