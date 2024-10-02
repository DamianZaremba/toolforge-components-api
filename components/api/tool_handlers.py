import logging

from fastapi import HTTPException

from ..models.api_models import (
    Message,
    ToolConfig,
    ToolConfigResponse,
)
from ..storage import Storage, ToolConfigNotFoundError

logger = logging.getLogger(__name__)


def retrieve_tool_config(toolname: str, storage: Storage) -> ToolConfigResponse:
    """Retrieve the configuration for a specific tool."""
    logger.info(f"Retrieving config for tool: {toolname}")
    try:
        config = storage.get_tool_config(toolname)
        logger.info(f"Config retrieved successfully for tool: {toolname}")
        return ToolConfigResponse(data=config, messages=Message())
    except ToolConfigNotFoundError as e:
        logger.warning(str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving config for tool {toolname}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


def modify_tool_config(
    toolname: str, config: ToolConfig, storage: Storage
) -> ToolConfigResponse:
    """Update the configuration for a specific tool."""
    logger.info(f"Modifying config for tool: {toolname}")
    try:
        storage.set_tool_config(toolname, config)
        logger.info(f"Config updated successfully for tool: {toolname}")
        return ToolConfigResponse(
            data=config,
            messages=Message(
                info=[
                    f"Configuration for {toolname} updated successfully. This is now the only stored configuration."
                ]
            ),
        )
    except Exception as e:
        logger.error(f"Error updating config for tool {toolname}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
