import logging
from abc import ABC, abstractmethod

from ..models.api_models import Deployment, ToolConfig

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
    def create_deployment(self, tool_name: str, deployment: Deployment) -> None:
        pass
