from fastapi import APIRouter, Depends

from ..models.api_models import (
    Deployment,
    DeploymentBuildInfo,
    DeploymentTokenResponse,
    ResponseMessages,
    ToolConfig,
    ToolConfigResponse,
    ToolDeploymentResponse,
)
from ..storage import Storage, get_storage
from . import tool_handlers as handlers
from .auth import ensure_authenticated

router = APIRouter(
    prefix="/tool",
    dependencies=[
        Depends(ensure_authenticated),
    ],
)


@router.get("/{toolname}/config")
def get_tool_config(
    toolname: str,
    storage: Storage = Depends(get_storage),
) -> ToolConfigResponse:
    """Retrieve the configuration for a specific tool."""
    config = handlers.get_tool_config(toolname, storage)
    return ToolConfigResponse(data=config, messages=ResponseMessages())


@router.post("/{toolname}/config")
def update_tool_config(
    toolname: str,
    config: ToolConfig,
    storage: Storage = Depends(get_storage),
) -> ToolConfigResponse:
    """Update or create the configuration for a specific tool."""
    updated_config = handlers.update_tool_config(toolname, config, storage)
    return ToolConfigResponse(
        data=updated_config,
        messages=ResponseMessages(
            info=[f"Configuration for {toolname} updated successfully."]
        ),
    )


@router.delete("/{toolname}/config")
def delete_tool_config(
    toolname: str,
    storage: Storage = Depends(get_storage),
) -> ToolConfigResponse:
    """Delete the configuration for a specific tool."""
    config = handlers.delete_tool_config(toolname, storage)
    return ToolConfigResponse(data=config, messages=ResponseMessages())


# This route should be above the get_tool_deployment route or {deploy_id} will match any string, including the token
@router.get("/{toolname}/deployment/token")
def get_tool_deployment_token(
    toolname: str,
    storage: Storage = Depends(get_storage),
) -> DeploymentTokenResponse:
    token = handlers.get_deployment_token(toolname, storage)
    return DeploymentTokenResponse(data=token, messages=ResponseMessages())


@router.get("/{toolname}/deployment/{deployment_id}")
def get_tool_deployment(
    toolname: str,
    deployment_id: str,
    storage: Storage = Depends(get_storage),
) -> ToolDeploymentResponse:
    """Retrieve the configuration for a specific tool."""
    deployment = handlers.get_tool_deployment(
        tool_name=toolname, deployment_name=deployment_id, storage=storage
    )
    return ToolDeploymentResponse(data=deployment, messages=ResponseMessages())


@router.post("/{toolname}/deployment")
def create_tool_deployment(
    toolname: str,
    storage: Storage = Depends(get_storage),
) -> ToolDeploymentResponse:
    """Create a new tool deployment."""
    tool_config = handlers.get_tool_config(toolname=toolname, storage=storage)
    # TODO: actually get the list of builds we want to trigger
    builds = {
        component_name: DeploymentBuildInfo(build_id="TODO")
        for component_name, component_info in tool_config.components.items()
        if component_info.build.ref
    }
    new_deployment = Deployment.get_new_deployment(
        tool_name=toolname,
        builds=builds,
    )
    handlers.create_tool_deployment(
        tool_name=toolname, deployment=new_deployment, storage=storage
    )
    return ToolDeploymentResponse(
        data=new_deployment,
        messages=ResponseMessages(
            info=[f"Deployment for {toolname} created successfully."]
        ),
    )


@router.post("/{toolname}/deployment/token")
def create_tool_deployment_token(
    toolname: str,
    storage: Storage = Depends(get_storage),
) -> DeploymentTokenResponse:
    token = handlers.create_deployment_token(toolname, storage)
    return DeploymentTokenResponse(
        data=token,
        messages=ResponseMessages(
            info=[f"Deployment token for {toolname} created successfully."]
        ),
    )


@router.delete("/{toolname}/deployment/token")
def delete_tool_deployment_token(
    toolname: str,
    storage: Storage = Depends(get_storage),
) -> ResponseMessages:
    handlers.delete_deployment_token(toolname, storage)
    return ResponseMessages(
        info=[f"Deployment token for {toolname} deleted successfully."]
    )
