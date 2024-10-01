from typing import Literal, Optional, TypeAlias

from pydantic import AnyUrl, BaseModel, Field, field_validator

ComponentType: TypeAlias = Literal["continuous", "scheduled", "one-off"]


class BuildInfo(BaseModel):
    repository: AnyUrl
    ref: Optional[str] = "main"


class ComponentInfo(BaseModel):
    component_type: ComponentType
    build: BuildInfo


class ToolConfig(BaseModel):
    config_version: str
    components: dict[str, ComponentInfo] = Field(..., min_length=1)

    @field_validator("components")
    @classmethod
    def check_components_not_empty(cls, v: dict) -> dict:
        if not v:
            raise ValueError("ToolConfig must contain at least one component")
        return v


class Message(BaseModel):
    info: list[str] = []
    warning: list[str] = []
    error: list[str] = []


class ApiResponse(BaseModel):
    data: Optional[dict] = None
    messages: Message = Message()


class ToolConfigResponse(ApiResponse):
    data: ToolConfig
