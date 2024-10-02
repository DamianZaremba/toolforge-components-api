from typing import Generic, Literal, Optional, TypeAlias, TypeVar

from pydantic import AnyUrl, BaseModel, Field

ComponentType: TypeAlias = Literal["continuous", "scheduled", "one-off"]
T = TypeVar("T")


class BuildInfo(BaseModel):
    repository: AnyUrl
    ref: Optional[str] = "refs/heads/main"


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


ToolConfigResponse = ApiResponse[ToolConfig]
HealthzResponse = ApiResponse[HealthState]
