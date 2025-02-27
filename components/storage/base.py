import logging
from abc import ABC, abstractmethod

from ..models.api_models import Deployment, DeployToken, ToolConfig

logger = logging.getLogger(__name__)


class Storage(ABC):
    @abstractmethod
    def get_tool_config(self, tool_name: str) -> ToolConfig:
        pass

    @abstractmethod
    def set_tool_config(self, tool_name: str, config: ToolConfig) -> None:
        pass

    @abstractmethod
    def delete_tool_config(self, tool_name: str) -> ToolConfig:
        pass

    @abstractmethod
    def get_deployment(self, tool_name: str, deployment_name: str) -> Deployment:
        pass

    @abstractmethod
    def list_deployments(self, tool_name: str) -> list[Deployment]:
        pass

    @abstractmethod
    def create_deployment(self, tool_name: str, deployment: Deployment) -> None:
        pass

    @abstractmethod
    def update_deployment(self, tool_name: str, deployment: Deployment) -> None:
        pass

    @abstractmethod
    def delete_deployment(self, tool_name: str, deployment_name: str) -> Deployment:
        pass

    @abstractmethod
    def get_deploy_token(self, tool_name: str) -> DeployToken:
        pass

    @abstractmethod
    def set_deploy_token(self, tool_name: str, token: DeployToken) -> None:
        pass

    @abstractmethod
    def delete_deploy_token(self, tool_name: str) -> DeployToken:
        pass
