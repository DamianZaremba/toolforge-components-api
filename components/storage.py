import logging
from abc import ABC, abstractmethod

from fastapi import Depends

from .models.api_models import ToolConfig
from .settings import Settings, get_settings

logger = logging.getLogger(__name__)


class Storage(ABC):
    @abstractmethod
    def get_tool_config(self, toolname: str) -> ToolConfig:
        pass

    @abstractmethod
    def set_tool_config(self, toolname: str, config: ToolConfig) -> None:
        pass


class ToolConfigNotFoundError(Exception):
    pass


class MockStorage(Storage):
    def __init__(self):
        self.tool_configs = {}
        logger.info("MockStorage initialized.")

    def get_tool_config(self, toolname: str) -> ToolConfig:
        logger.info(f"Attempting to get config for tool: {toolname}")
        if toolname not in self.tool_configs:
            raise ToolConfigNotFoundError(
                f"No configuration found for tool: {toolname}"
            )
        return self.tool_configs[toolname]

    def set_tool_config(self, toolname: str, config: ToolConfig) -> None:
        logger.info(f"Setting config for tool: {toolname}")
        self.tool_configs[toolname] = config


# Important: Create a single instance of MockStorage
mock_storage = MockStorage()


class KubernetesStorage(Storage):
    def get_tool_config(self, toolname: str) -> ToolConfig:
        raise NotImplementedError(
            "KubernetesStorage.get_tool_config is not implemented."
        )

    def set_tool_config(self, toolname: str, config: ToolConfig) -> None:
        raise NotImplementedError(
            "KubernetesStorage.set_tool_config is not implemented."
        )


def get_storage(settings: Settings = Depends(get_settings)) -> Storage:
    if settings.storage_type == "mock":
        logger.info("Returning mock storage")
        return mock_storage
    elif settings.storage_type == "kubernetes":
        logger.info("Returning kubernetes storage")
        return KubernetesStorage()
    else:
        raise ValueError(f"Invalid storage type: {settings.storage_type}")
