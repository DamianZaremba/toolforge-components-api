import logging

from ..models.api_models import Deployment, DeployToken, ToolConfig
from .base import Storage
from .exceptions import NotFoundInStorage

logger = logging.getLogger(__name__)


class MockStorage(Storage):
    def __init__(self) -> None:
        self._tool_configs: dict[str, ToolConfig] = {}
        self._per_tool_deployments: dict[str, dict[str, Deployment]] = {}
        self._deploy_tokens: dict[str, DeployToken] = {}
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

    def get_deploy_token(self, tool_name: str) -> DeployToken:
        logger.info(f"Retrieving deploy token for tool: {tool_name}")
        token = self._deploy_tokens.get(tool_name)
        if not token:
            logger.warning(f"No deploy token found for tool: {tool_name}")
            raise NotFoundInStorage(f"No deploy token found for tool: {tool_name}")
        logger.info(f"Found token {token.token} for tool: {tool_name}")
        return token

    def set_deploy_token(self, tool_name: str, token: DeployToken) -> None:
        logger.info(f"Setting deploy token for tool: {tool_name}")
        self._deploy_tokens[tool_name] = token
        logger.info(f"Deploy token set for tool: {tool_name}")

    def delete_deploy_token(self, tool_name: str) -> DeployToken:
        logger.info(f"Deleting deploy token for tool: {tool_name}")
        if tool_name not in self._deploy_tokens:
            raise NotFoundInStorage(f"No deploy token found for tool: {tool_name}")
        token = self._deploy_tokens.pop(tool_name)
        logger.info(f"Deploy token deleted for tool: {tool_name}")
        return token
