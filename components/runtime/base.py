import logging
from abc import ABC, abstractmethod
from typing import TypeAlias

from ..gen.toolforge_models import (
    BuildsBuild,
    JobsDefinedContinuousJob,
    JobsDefinedOneOffJob,
    JobsDefinedScheduledJob,
)
from ..models.api_models import (
    ComponentInfo,
    DeploymentBuildInfo,
    DeploymentBuildState,
    SourceBuildInfo,
)

logger = logging.getLogger(__name__)


AnyDefinedJob: TypeAlias = (
    JobsDefinedOneOffJob | JobsDefinedScheduledJob | JobsDefinedContinuousJob
)


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
        force_restart: bool,
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
    def get_jobs(self, tool_name: str) -> list[AnyDefinedJob]:
        pass

    @abstractmethod
    def get_builds(self, tool_name: str) -> list[BuildsBuild]:
        pass

    @abstractmethod
    def cancel_build(self, tool_name: str, build_id: str) -> None:
        pass
