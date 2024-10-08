import logging

from ..models.api_models import Deployment, ToolConfig
from .base import Storage
from .exceptions import NotFoundInStorage

logger = logging.getLogger(__name__)


class MockStorage(Storage):
    def __init__(self) -> None:
        self._tool_configs: dict[str, ToolConfig] = {}
        self._per_tool_deployments: dict[str, dict[str, Deployment]] = {}
        logger.info("MockStorage initialized.")

    def get_tool_config(self, tool_name: str) -> ToolConfig:
        logger.info(f"Attempting to get config for tool: {tool_name}")
        if tool_name not in self._tool_configs:
            raise NotFoundInStorage(f"No configuration found for tool: {tool_name}")
        return self._tool_configs[tool_name]

    def set_tool_config(self, tool_name: str, config: ToolConfig) -> None:
        logger.info(f"Setting config for tool: {tool_name}")
        self._tool_configs[tool_name] = config

    def delete_tool_config(self, tool_name: str) -> ToolConfig:
        logger.info(f"Deleting config for tool: {tool_name}")
        if tool_name not in self._tool_configs:
            raise NotFoundInStorage(f"No configuration found for tool: {tool_name}")
        return self._tool_configs.pop(tool_name)

    def get_deployment(self, tool_name: str, deployment_name: str) -> Deployment:
        try:
            return self._per_tool_deployments[tool_name][deployment_name]
        except KeyError as error:
            raise NotFoundInStorage(
                f"No deployments found for tool: {tool_name}"
            ) from error

    def create_deployment(self, tool_name: str, deployment: Deployment) -> None:
        if tool_name not in self._per_tool_deployments:
            self._per_tool_deployments[tool_name] = {}

        self._per_tool_deployments[tool_name][deployment.deploy_id] = deployment
