import datetime
import random
import string
from enum import Enum
from typing import (
    Annotated,
    Any,
    ClassVar,
    Generic,
    Literal,
    Type,
    TypeAlias,
    TypeVar,
    Union,
)
from uuid import UUID, uuid4

from pydantic import BaseModel, Discriminator, Field, Tag

# TODO: add the others when we add support for them
ComponentType: TypeAlias = Literal["continuous"]
T = TypeVar("T")


class ConfigVersion(str, Enum):
    V1_BETA1 = "v1beta1"


class BuildInfo(BaseModel):
    use_prebuilt: str


def build_info_discriminator(value: Any) -> str | None:
    if isinstance(value, dict):
        if value.get("use_prebuilt"):
            return "prebuilt_build_info_tag"
        elif value.get("repository"):
            return "source_build_info_tag"
    elif isinstance(value, SourceBuildInfo):
        return "source_build_info_tag"
    elif isinstance(value, PrebuiltBuildInfo):
        return "prebuilt_build_info_tag"

    return None


class PrebuiltBuildInfo(BaseModel):
    use_prebuilt: str


class SourceBuildInfo(BaseModel):
    repository: str
    ref: str


class RunInfo(BaseModel):
    command: str


class ComponentInfo(BaseModel):
    component_type: ComponentType
    build: Annotated[
        Union[
            Annotated[SourceBuildInfo, Tag("source_build_info_tag")],
            Annotated[PrebuiltBuildInfo, Tag("prebuilt_build_info_tag")],
        ],
        Discriminator(discriminator=build_info_discriminator),
    ]
    run: RunInfo


class ToolConfig(BaseModel):
    config_version: Literal[ConfigVersion.V1_BETA1] | None = ConfigVersion.V1_BETA1
    components: dict[str, ComponentInfo] = Field(..., min_length=1)


class DeploymentBuildState(str, Enum):
    pending = "pending"
    running = "running"
    failed = "failed"
    successful = "successful"
    unknown = "unknown"


class DeploymentBuildInfo(BaseModel):
    NO_ID_YET: ClassVar[str] = "no-id-yet"
    NO_BUILD_NEEDED: ClassVar[str] = "no-build-needed"
    build_id: str | Literal["no-id-yet", "no-build-needed"]
    build_status: DeploymentBuildState


class DeploymentRunState(str, Enum):
    """
    This are the states a run can be in

    A run being an execution of a component (ex. running a continuous job, or creating a new scheduled job).
    """

    pending = "pending"
    failed = "failed"
    successful = "successful"
    skipped = "skipped"
    unknown = "unknown"


class DeploymentRunInfo(BaseModel):
    run_status: DeploymentRunState
    run_long_status: str = ""


class DeploymentState(str, Enum):
    pending = "pending"
    running = "running"
    failed = "failed"
    timed_out = "timed_out"
    successful = "successful"


class Deployment(BaseModel):
    deploy_id: str
    creation_time: str
    builds: dict[str, DeploymentBuildInfo]
    runs: dict[str, DeploymentRunInfo]
    status: DeploymentState = DeploymentState.pending
    long_status: str = ""

    @classmethod
    def get_new_deployment(
        cls: "Type[Deployment]",
        builds: dict[str, DeploymentBuildInfo],
        runs: dict[str, DeploymentRunInfo],
    ) -> "Deployment":
        cur_timestamp = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%d-%H%M%S")
        new_id = f"{cur_timestamp}-"
        # We rely on random having enough entropy and having little requests per second requests to not collide.
        random_suffix = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=10)
        )
        new_id += random_suffix
        return Deployment(
            creation_time=cur_timestamp,
            deploy_id=new_id,
            builds=builds,
            runs=runs,
        )


class DeployToken(BaseModel):
    token: UUID = Field(default_factory=uuid4)
    creation_date: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(tz=datetime.UTC)
    )


class DeploymentList(BaseModel):
    deployments: list[Deployment]


class HealthState(BaseModel):
    status: Literal["OK", "ERROR"]


BETA_WARNING_MESSAGE = "You are using a beta feature of Toolforge."


class ResponseMessages(BaseModel):
    info: list[str] = []
    warning: list[str] = [BETA_WARNING_MESSAGE]
    error: list[str] = []


class ApiResponse(BaseModel, Generic[T]):
    data: T
    messages: ResponseMessages = ResponseMessages()


ToolConfigResponse = ApiResponse[ToolConfig]
HealthzResponse = ApiResponse[HealthState]
ToolDeploymentResponse = ApiResponse[Deployment]
DeployTokenResponse = ApiResponse[DeployToken]
ToolDeploymentListResponse = ApiResponse[DeploymentList]
