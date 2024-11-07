from fastapi import APIRouter, BackgroundTasks, Depends

from ..models.api_models import (
    Deployment,
    DeploymentBuildInfo,
    DeployTokenResponse,
    ResponseMessages,
    ToolConfig,
    ToolConfigResponse,
    ToolDeploymentResponse,
)
from ..storage import Storage, get_storage
from . import tool_handlers as handlers
from .auth import ensure_authenticated, ensure_token_or_auth

# Used for most requests, authenticates only with the header
header_auth_router = APIRouter(
    prefix="/tool",
    dependencies=[
        Depends(ensure_authenticated),
    ],
)

# Used only for deployment creation, authenticates with both, token and header
token_auth_router = APIRouter(
    prefix="/tool",
    dependencies=[
        Depends(ensure_token_or_auth),
    ],
)


@header_auth_router.get("/{toolname}/config")
def get_tool_config(
    toolname: str,
    storage: Storage = Depends(get_storage),
) -> ToolConfigResponse:
    """Retrieve the configuration for a specific tool."""
    config = handlers.get_tool_config(toolname, storage)
    return ToolConfigResponse(data=config, messages=ResponseMessages())


@header_auth_router.post("/{toolname}/config")
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


@header_auth_router.delete("/{toolname}/config")
def delete_tool_config(
    toolname: str,
    storage: Storage = Depends(get_storage),
) -> ToolConfigResponse:
    """Delete the configuration for a specific tool."""
    config = handlers.delete_tool_config(toolname, storage)
    return ToolConfigResponse(data=config, messages=ResponseMessages())


# This route should be above the get_tool_deployment route or {deployment_id} will match any string, including the token
@header_auth_router.get("/{toolname}/deployment/token")
def get_tool_deploy_token(
    toolname: str,
    storage: Storage = Depends(get_storage),
) -> DeployTokenResponse:
    token = handlers.get_deploy_token(toolname, storage)
    return DeployTokenResponse(data=token, messages=ResponseMessages())


@header_auth_router.get("/{toolname}/deployment/{deployment_id}")
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


@token_auth_router.post("/{toolname}/deployment")
def create_tool_deployment(
    toolname: str,
    background_tasks: BackgroundTasks,
    storage: Storage = Depends(get_storage),
) -> ToolDeploymentResponse:
    """Create a new tool deployment."""
    tool_config = handlers.get_tool_config(toolname=toolname, storage=storage)
    # TODO: actually get the list of builds we want to trigger
    builds = {
        component_name: DeploymentBuildInfo(build_id="TODO")
        for component_name, component_info in tool_config.components.items()
        if component_info.build and component_info.build.use_prebuilt
    }
    new_deployment = Deployment.get_new_deployment(
        tool_name=toolname,
        builds=builds,
    )
    handlers.create_tool_deployment(
        tool_name=toolname,
        deployment=new_deployment,
        storage=storage,
        background_tasks=background_tasks,
    )
    return ToolDeploymentResponse(
        data=new_deployment,
        messages=ResponseMessages(
            info=[f"Deployment for {toolname} created successfully."]
        ),
    )


@header_auth_router.post("/{toolname}/deployment/token")
def create_tool_deploy_token(
    toolname: str,
    storage: Storage = Depends(get_storage),
) -> DeployTokenResponse:
    token = handlers.create_deploy_token(toolname, storage)
    return DeployTokenResponse(
        data=token,
        messages=ResponseMessages(
            info=[f"Deploy token for {toolname} created successfully."]
        ),
    )


@header_auth_router.delete("/{toolname}/deployment/token")
def delete_tool_deploy_token(
    toolname: str,
    storage: Storage = Depends(get_storage),
) -> DeployTokenResponse:
    token = handlers.delete_deploy_token(toolname, storage)
    return DeployTokenResponse(
        data=token,
        messages=ResponseMessages(
            info=[f"Deploy token for {toolname} deleted successfully."]
        ),
    )


@header_auth_router.delete("/{toolname}/deployment/{deployment_id}")
def delete_tool_deployment(
    toolname: str, deployment_id: str, storage: Storage = Depends(get_storage)
) -> ToolDeploymentResponse:
    deployment = handlers.delete_tool_deployment(toolname, deployment_id, storage)
    return ToolDeploymentResponse(
        data=deployment,
        messages=ResponseMessages(
            info=[f"Deployment {deployment_id} deleted successfully."]
        ),
    )
