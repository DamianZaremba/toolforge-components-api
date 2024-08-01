from typing import Optional

from pydantic import BaseModel


class Config(BaseModel):
    pass


class Deployment(BaseModel):
    deploy_id: str
    toolname: str
    status: str


class Message(BaseModel):
    info: list[str] = []
    warning: list[str] = []
    error: list[str] = []


class ApiResponse(BaseModel):
    data: Optional[dict] = None
    messages: Message = Message()


class ConfigResponse(ApiResponse):
    data: dict


class DeploymentResponse(ApiResponse):
    data: Deployment


class ConfigUpdateRequest(BaseModel):
    config: Config
