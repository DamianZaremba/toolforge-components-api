import logging

from fastapi import HTTPException

from ..models.api_models import (
    Deployment,
    DeploymentToken,
    ToolConfig,
)
from ..storage import Storage
from ..storage.exceptions import NotFoundInStorage

logger = logging.getLogger(__name__)


def get_tool_config(toolname: str, storage: Storage) -> ToolConfig:
    logger.info(f"Retrieving config for tool: {toolname}")
    try:
        config = storage.get_tool_config(toolname)
        logger.info(f"Config retrieved successfully for tool: {toolname}")
        return config
    except NotFoundInStorage as e:
        logger.warning(str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving config for tool {toolname}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


def update_tool_config(
    toolname: str, config: ToolConfig, storage: Storage
) -> ToolConfig:
    logger.info(f"Modifying config for tool: {toolname}")
    try:
        storage.set_tool_config(toolname, config)
        logger.info(f"Config updated successfully for tool: {toolname}")
        return config
    except Exception as e:
        logger.error(f"Error updating config for tool {toolname}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def delete_tool_config(toolname: str, storage: Storage) -> ToolConfig:
    logger.info(f"Deleting config for tool: {toolname}")
    try:
        old_config = storage.delete_tool_config(toolname)
        logger.info(f"Config deleted successfully for tool: {toolname}")
        return old_config
    except Exception as e:
        logger.error(f"Error deleting config for tool {toolname}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def get_tool_deployment(
    tool_name: str, deployment_name: str, storage: Storage
) -> Deployment:
    logger.info(f"Retrieving deployment {deployment_name} for tool {tool_name}")
    try:
        config = storage.get_deployment(
            tool_name=tool_name, deployment_name=deployment_name
        )
        logger.info(f"Deployment retrieved successfully for tool: {tool_name}")
        return config

    except NotFoundInStorage as e:
        logger.warning(str(e))
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        logger.error(f"Error retrieving deployment for tool {tool_name}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


def create_tool_deployment(
    tool_name: str, deployment: Deployment, storage: Storage
) -> Deployment:
    logger.info(f"Creating deployment for tool: {tool_name}")
    try:
        storage.create_deployment(tool_name=tool_name, deployment=deployment)
        logger.info(f"Created deployment {deployment} for tool {tool_name}")
        return deployment
    except Exception as e:
        logger.error(
            f"Error creating deployment {deployment} for tool {tool_name}: {str(e)}"
        )
        raise HTTPException(status_code=500, detail=str(e))


def create_deployment_token(toolname: str, storage: Storage) -> DeploymentToken:
    logger.info(f"Creating deployment token for tool: {toolname}")
    try:
        new_token = storage.create_deployment_token(toolname)
        logger.info(f"Deployment token created for tool: {toolname}")
        return new_token
    except Exception as e:
        logger.error(f"Error creating deployment token for tool {toolname}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


def get_deployment_token(toolname: str, storage: Storage) -> DeploymentToken:
    logger.info(f"Retrieving deployment token for tool: {toolname}")
    try:
        token = storage.get_deployment_token(toolname)
        logger.info(f"Deployment token retrieved for tool: {toolname}")
        return token
    except NotFoundInStorage as e:
        logger.warning(str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving deployment token for tool {toolname}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


def delete_deployment_token(toolname: str, storage: Storage) -> None:
    logger.info(f"Deleting deployment token for tool: {toolname}")
    try:
        storage.delete_deployment_token(toolname)
        logger.info(f"Deployment token deleted for tool: {toolname}")
    except NotFoundInStorage as e:
        logger.warning(str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting deployment token for tool {toolname}: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
