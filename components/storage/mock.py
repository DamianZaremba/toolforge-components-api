import logging
from uuid import uuid4

from ..models.api_models import Deployment, DeploymentToken, ToolConfig
from .base import Storage
from .exceptions import NotFoundInStorage

logger = logging.getLogger(__name__)


class MockStorage(Storage):
    def __init__(self) -> None:
        self._tool_configs: dict[str, ToolConfig] = {}
        self._per_tool_deployments: dict[str, dict[str, Deployment]] = {}
        self._deployment_tokens: dict[str, DeploymentToken] = {}
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

    def get_deployment_token(self, tool_name: str) -> DeploymentToken:
        logger.info(f"Retrieving deployment token for tool: {tool_name}")
        token = self._deployment_tokens.get(tool_name)
        if not token:
            logger.warning(f"No deployment token found for tool: {tool_name}")
            raise NotFoundInStorage(f"No deployment token found for tool: {tool_name}")
        logger.info(f"Found token {token.token} for tool: {tool_name}")
        return token

    def create_deployment_token(self, tool_name: str) -> DeploymentToken:
        logger.info(f"Creating deployment token for tool: {tool_name}")
        new_token = DeploymentToken(token=uuid4())
        self._deployment_tokens[tool_name] = new_token
        logger.info(f"Deployment token created for tool: {tool_name}")
        return new_token

    def delete_deployment_token(self, tool_name: str) -> None:
        logger.info(f"Deleting deployment token for tool: {tool_name}")
        if tool_name not in self._deployment_tokens:
            raise NotFoundInStorage(f"No deployment token found for tool: {tool_name}")
        del self._deployment_tokens[tool_name]
        logger.info(f"Deployment token deleted for tool: {tool_name}")
