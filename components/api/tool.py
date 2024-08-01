from fastapi import APIRouter

from components.api.tool_handlers import (
    create_deployment,
    get_deployment,
    get_tool_config,
    update_tool_config,
)
from components.models.pydantic import (
    ApiResponse,
    ConfigResponse,
    ConfigUpdateRequest,
    DeploymentResponse,
)

router = APIRouter(prefix="/tool")


@router.get("/{toolname}/config", response_model=ConfigResponse)
def get_config(toolname: str):
    return get_tool_config(toolname)


@router.post("/{toolname}/config", response_model=ApiResponse)
def update_config(toolname: str, config_request: ConfigUpdateRequest):
    return update_tool_config(toolname, config_request.config)


@router.post("/{toolname}/deploy", response_model=DeploymentResponse)
def create_deploy(toolname: str):
    return create_deployment(toolname)


@router.get("/{toolname}/deploy/{deploy_id}", response_model=DeploymentResponse)
def get_deploy(toolname: str, deploy_id: str):
    return get_deployment(toolname, deploy_id)
