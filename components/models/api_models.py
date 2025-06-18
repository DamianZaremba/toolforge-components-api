import datetime
import random
import string
from enum import Enum
from typing import (
    Annotated,
    ClassVar,
    Generic,
    Literal,
    Optional,
    Self,
    Type,
    TypeAlias,
    TypeVar,
)
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, Tag, model_validator

# TODO: add the others when we add support for them
ComponentType: TypeAlias = Literal["continuous"]
T = TypeVar("T")


class ConfigVersion(str, Enum):
    V1_BETA1 = "v1beta1"


class SourceBuildInfo(BaseModel):
    repository: str = Field(
        description="URL of the public git repository with the code to build.",
        examples=[
            "https://gitlab.wikimedia.org/toolforge-repos/sample-complex-app-backend"
        ],
    )
    # TODO: maybe make this optional?
    # we don't really need a ref as providing just repository should default to default ref no?
    ref: str = Field(
        description="Git ref to build from. This can be a tag, a branch name or a commit SHA.",
        examples=["main", "v1.2.3", "35b594f5d452c288c4a15fe667a7dfb94a7e5489"],
    )


# TODO: split into base, one-off, scheduled and continuous when we support one-off and scheduled?
class RunInfo(BaseModel):
    command: str = Field(
        description=(
            "Command to use to run this component, `launcher` will be prepended to it to load the "
            "environment if needed."
        ),
        examples=["bash -c 'while date; do sleep 10; done'"],
    )
    port: Optional[int] = Field(
        default=None,
        description=(
            "Port where the service listens on. Other components can then address this one with "
            "`http://<this_component_name>:<port>`"
        ),
        examples=[8080],
    )
    health_check_script: Optional[str] = Field(
        default=None,
        description=(
            "Script/command to run to check that the service is running correctly. This will run inside the same "
            "container as the service itself."
        ),
        examples=["test -e /tmp/everything_is_ok"],
    )
    health_check_http: Optional[str] = Field(
        default=None,
        description="HTTP path to query for the status of the system. It expects an HTTP 200 OK response, anything else is interpreted as failure.",
        examples=["/healthz"],
    )

    @model_validator(mode="after")
    def validate_health_check(self) -> Self:
        if self.health_check_script and self.health_check_http:
            raise ValueError(
                "Cannot specify both health_check_script and health_check_http"
            )
        return self


class ComponentInfo(BaseModel):
    component_type: ComponentType = Field(
        examples=["continuous"],
        description="Type of component, currently only `continuous` is supported.",
    )
    build: Annotated[SourceBuildInfo, Tag("source_build_info_tag")] = Field(
        description="Parameters for building the component."
    )
    run: RunInfo = Field(description="Parameters describing how to run this component.")


class ToolConfig(BaseModel):
    config_version: Literal[ConfigVersion.V1_BETA1] | None = Field(
        examples=["v1beta1"], default=ConfigVersion.V1_BETA1
    )
    components: dict[str, ComponentInfo] = Field(
        ...,
        description=(
            "List of components to run. Each component matches a continuous job, scheduled job, one-off job or "
            "webservice."
        ),
        min_length=1,
    )


class DeploymentBuildState(str, Enum):
    pending = "pending"
    running = "running"
    failed = "failed"
    successful = "successful"
    unknown = "unknown"
    skipped = "skipped"


class DeploymentBuildInfo(BaseModel):
    NO_ID_YET: ClassVar[str] = "no-id-yet"
    NO_BUILD_NEEDED: ClassVar[str] = "no-build-needed"
    build_id: str | Literal["no-id-yet", "no-build-needed"]
    build_status: DeploymentBuildState
    build_long_status: str = ""


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
    force_build: bool = False
    force_run: bool = False

    @classmethod
    def get_new_deployment(
        cls: "Type[Deployment]",
        builds: dict[str, DeploymentBuildInfo],
        runs: dict[str, DeploymentRunInfo],
        force_build: bool = False,
        force_run: bool = False,
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
            force_build=force_build,
            force_run=force_run,
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


EXAMPLE_GENERATED_CONFIG = ToolConfig(
    components={
        "component1": ComponentInfo(
            component_type="continuous",
            build=SourceBuildInfo(
                ref="main",
                repository="https://gitlab.wikimedia.org/toolforge-repos/sample-static-buildpack-app",
            ),
            run=RunInfo(
                command="while true; do echo 'hello world from component1'; sleep 10; done",
                health_check_http="/healthz",
            ),
        ),
        "component2": ComponentInfo(
            component_type="continuous",
            build=SourceBuildInfo(
                ref="dummy_branch",
                repository="https://gitlab.wikimedia.org/toolforge-repos/sample-static-buildpack-app",
            ),
            run=RunInfo(
                command="while true; do touch /tmp/everything_ok; echo 'hello world from component2'; sleep 10; done",
                health_check_script="test -e /tmp/everything_ok",
            ),
        ),
    }
)
