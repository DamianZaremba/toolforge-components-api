from fastapi import APIRouter, Depends

from ..models.api_models import (
    ToolConfig,
    ToolConfigResponse,
)
from ..storage import Storage, get_storage
from .tool_handlers import (
    modify_tool_config,
    retrieve_tool_config,
)

router = APIRouter()


@router.get("/tool/{toolname}/config", response_model=ToolConfigResponse)
def get_tool_config(toolname: str, storage: Storage = Depends(get_storage)):
    """Retrieve the configuration for a specific tool."""
    return retrieve_tool_config(toolname, storage)


@router.post("/tool/{toolname}/config", response_model=ToolConfigResponse)
def update_tool_config(
    toolname: str, config: ToolConfig, storage: Storage = Depends(get_storage)
):
    """Update or create the configuration for a specific tool."""
    return modify_tool_config(toolname, config, storage)
