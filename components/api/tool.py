from fastapi import APIRouter, Depends

from ..models.api_models import (
    ResponseMessages,
    ToolConfig,
    ToolConfigResponse,
)
from ..storage import Storage, get_storage
from .tool_handlers import (
    modify_tool_config,
    retrieve_tool_config,
)

router = APIRouter()


@router.get("/tool/{toolname}/config")
def get_tool_config(
    toolname: str, storage: Storage = Depends(get_storage)
) -> ToolConfigResponse:
    """Retrieve the configuration for a specific tool."""
    config = retrieve_tool_config(toolname, storage)
    return ToolConfigResponse(data=config, messages=ResponseMessages())


@router.post("/tool/{toolname}/config")
def update_tool_config(
    toolname: str, config: ToolConfig, storage: Storage = Depends(get_storage)
) -> ToolConfigResponse:
    """Update or create the configuration for a specific tool."""
    updated_config = modify_tool_config(toolname, config, storage)
    return ToolConfigResponse(
        data=updated_config,
        messages=ResponseMessages(
            info=[
                f"Configuration for {toolname} updated successfully. This is now the only stored configuration."
            ]
        ),
    )
