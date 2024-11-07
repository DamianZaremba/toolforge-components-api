import logging
from abc import ABC, abstractmethod

from ..models.api_models import Deployment, DeployToken, ToolConfig

logger = logging.getLogger(__name__)


class Storage(ABC):
    @abstractmethod
    async def get_tool_config(self, tool_name: str) -> ToolConfig:
        pass

    @abstractmethod
    async def set_tool_config(self, tool_name: str, config: ToolConfig) -> None:
        pass

    @abstractmethod
    async def delete_tool_config(self, tool_name: str) -> ToolConfig:
        pass

    @abstractmethod
    async def get_deployment(self, tool_name: str, deployment_name: str) -> Deployment:
        pass

    @abstractmethod
    async def create_deployment(self, tool_name: str, deployment: Deployment) -> None:
        pass

    @abstractmethod
    async def get_deploy_token(self, tool_name: str) -> DeployToken:
        pass

    @abstractmethod
    async def set_deploy_token(self, tool_name: str, token: DeployToken) -> None:
        pass

    @abstractmethod
    async def delete_deploy_token(self, tool_name: str) -> DeployToken:
        pass
