from logging import getLogger
from typing import cast

from toolforge_weld.api_client import ToolforgeClient

from .client import get_toolforge_client
from .gen.toolforge_models import JobsJobResponse, JobsNewJob
from .models.api_models import (
    ComponentInfo,
    Deployment,
    PrebuiltBuildInfo,
    RunInfo,
    SourceBuildInfo,
    ToolConfig,
)
from .settings import get_settings

logger = getLogger(__name__)


def _get_component_image_name(tool_name: str, component_info: ComponentInfo) -> str:
    match component_info.build:
        case PrebuiltBuildInfo():
            logger.debug(f"Got prebuilt build type: {component_info}")
            return component_info.build.use_prebuilt
        case SourceBuildInfo():
            logger.debug(f"Got source build type: {component_info}")
            # TODO: use the actual build logs/info to get the image name once we trigger builds
            return f"tool-{tool_name}/tool-{tool_name}:latest"

    logger.error(f"Unsupported build information: {component_info.build}")
    raise Exception(f"unsupported build information: {component_info.build}")


def do_deploy(
    tool_name: str,
    tool_config: ToolConfig,
    deployment: Deployment,
) -> None:
    logger.info(f"Starting deployment for tool {tool_name}")
    toolforge_client = get_toolforge_client()
    for component_name, component_info in tool_config.components.items():
        # TODO: add support to load all the components jobs and then sync the current status
        if component_info.component_type != "continuous":
            logger.info(
                f"{tool_name}: skipping component {component_name} (non continuous is not supported yet)"
            )
            continue

        logger.info(
            f"{tool_name}: deploying component {component_name}: {component_info}"
        )
        deploy_continuous_jobs(
            tool_name=tool_name,
            run_info=component_info.run,
            component_name=component_name,
            image_name=_get_component_image_name(
                tool_name=tool_name, component_info=component_info
            ),
            toolforge_client=toolforge_client,
        )


def deploy_continuous_jobs(
    tool_name: str,
    component_name: str,
    run_info: RunInfo,
    image_name: str,
    toolforge_client: ToolforgeClient,
) -> None:
    # TODO: support multiple run infos/jobs

    settings = get_settings()

    # TODO: delete all the other jobs that we don't manage
    logger.debug(
        f"Creating job for component {component_name} with image {image_name} and run_info {run_info}"
    )
    new_job = run_info_to_job(
        component_name=component_name, run_info=run_info, image_name=image_name
    )
    logger.debug(f"Sending job info {new_job}")
    create_response = cast(
        JobsJobResponse,
        # Using patch here does an upsert
        toolforge_client.patch(
            f"/jobs/v1/tool/{tool_name}/jobs/",
            json=new_job.model_dump(mode="json", exclude_none=True),
            verify=settings.verify_toolforge_api_cert,
        ),
    )
    logger.debug(f"Deployed continuous job {component_name}: {create_response}")


def run_info_to_job(
    component_name: str, run_info: RunInfo, image_name: str
) -> JobsNewJob:
    # TODO: the generator seems to make every parameter mandatory :/, try to fix that somehow
    return JobsNewJob(
        cmd=run_info.command,
        name=component_name,
        imagename=image_name,
        continuous=True,
        cpu=None,
        emails=None,
        filelog=None,
        filelog_stderr=None,
        filelog_stdout=None,
        health_check=None,
        memory=None,
        mount=None,
        port=None,
        replicas=None,
        retry=None,
        schedule=None,
    )
