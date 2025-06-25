import logging
from abc import ABC, abstractmethod

from ..gen.toolforge_models import BuildsBuild, JobsDefinedJob
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
    def get_build_statuses(
        self, build: DeploymentBuildInfo, tool_name: str
    ) -> tuple[DeploymentBuildState, str]:
        """Returns the current state, and a string representing the long status in human-readable form."""
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
    def run_scheduled_job(
        self,
        tool_name: str,
        component_name: str,
        component_info: ComponentInfo,
    ) -> str:
        pass

    @abstractmethod
    def delete_job_if_exists(
        self,
        tool_name: str,
        component_name: str,
    ) -> str:
        pass

    @abstractmethod
    def get_jobs(self, tool_name: str) -> list[JobsDefinedJob]:
        pass

    @abstractmethod
    def get_builds(self, tool_name: str) -> list[BuildsBuild]:
        pass

    @abstractmethod
    def cancel_build(self, tool_name: str, build_id: str) -> None:
        pass
