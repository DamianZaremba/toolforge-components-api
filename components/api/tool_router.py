from fastapi import APIRouter, Depends

from ..models.api_models import (
    Deployment,
    DeploymentBuildInfo,
    ResponseMessages,
    ToolConfig,
    ToolConfigResponse,
    ToolDeploymentResponse,
)
from ..storage import Storage, get_storage
from . import tool_handlers as handlers
from .auth import ensure_authenticated

router = APIRouter()


@router.get("/tool/{toolname}/config")
def get_tool_config(
    toolname: str,
    _: str = Depends(ensure_authenticated),
    storage: Storage = Depends(get_storage),
) -> ToolConfigResponse:
    """Retrieve the configuration for a specific tool."""
    config = handlers.get_tool_config(toolname, storage)
    return ToolConfigResponse(data=config, messages=ResponseMessages())


@router.post("/tool/{toolname}/config")
def update_tool_config(
    toolname: str,
    config: ToolConfig,
    _: str = Depends(ensure_authenticated),
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


@router.delete("/tool/{toolname}/config")
def delete_tool_config(
    toolname: str,
    _: str = Depends(ensure_authenticated),
    storage: Storage = Depends(get_storage),
) -> ToolConfigResponse:
    """Delete the configuration for a specific tool."""
    config = handlers.delete_tool_config(toolname, storage)
    return ToolConfigResponse(data=config, messages=ResponseMessages())


@router.get("/tool/{toolname}/deployment/{deployment_id}")
def get_tool_deployment(
    toolname: str,
    deployment_id: str,
    _: str = Depends(ensure_authenticated),
    storage: Storage = Depends(get_storage),
) -> ToolDeploymentResponse:
    """Retrieve the configuration for a specific tool."""
    deployment = handlers.get_tool_deployment(
        tool_name=toolname, deployment_name=deployment_id, storage=storage
    )
    return ToolDeploymentResponse(data=deployment, messages=ResponseMessages())


@router.post("/tool/{toolname}/deployment")
def create_tool_deployment(
    toolname: str,
    _: str = Depends(ensure_authenticated),
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
