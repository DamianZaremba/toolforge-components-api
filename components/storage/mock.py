import logging

from ..models.api_models import ToolConfig
from .base import Storage
from .exceptions import NotFoundInStorage

logger = logging.getLogger(__name__)


class MockStorage(Storage):
    def __init__(self) -> None:
        self.tool_configs: dict[str, ToolConfig] = {}
        logger.info("MockStorage initialized.")

    def get_tool_config(self, tool_name: str) -> ToolConfig:
        logger.info(f"Attempting to get config for tool: {tool_name}")
        if tool_name not in self.tool_configs:
            raise NotFoundInStorage(f"No configuration found for tool: {tool_name}")
        return self.tool_configs[tool_name]

    def set_tool_config(self, tool_name: str, config: ToolConfig) -> None:
        logger.info(f"Setting config for tool: {tool_name}")
        self.tool_configs[tool_name] = config

    def delete_tool_config(self, tool_name: str) -> ToolConfig:
        logger.info(f"Deleting config for tool: {tool_name}")
        if tool_name not in self.tool_configs:
            raise NotFoundInStorage(f"No configuration found for tool: {tool_name}")
        return self.tool_configs.pop(tool_name)
