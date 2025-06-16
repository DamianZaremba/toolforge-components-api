import logging
from abc import ABC, abstractmethod

from ..models.api_models import (
    ComponentInfo,
    DeploymentBuildInfo,
    DeploymentBuildState,
    SourceBuildInfo,
)

logger = logging.getLogger(__name__)


class Runtime(ABC):
    @abstractmethod
    def start_build(
        self,
        build: SourceBuildInfo,
        tool_name: str,
        component_name: str,
        component_info: ComponentInfo,
        force_build: bool,
    ) -> DeploymentBuildInfo:
        pass

    @abstractmethod
    def get_build_status(
        self, build: DeploymentBuildInfo, tool_name: str
    ) -> DeploymentBuildState:
        pass

    @abstractmethod
    def run_continuous_job(
        self,
        tool_name: str,
        component_name: str,
        component_info: ComponentInfo,
    ) -> str:
        pass

    @abstractmethod
    def delete_continuous_job_if_exists(
        self,
        tool_name: str,
        component_name: str,
    ) -> str:
        pass
