from logging import getLogger
from typing import cast

from toolforge_weld.async_api_client import ToolforgeAsyncClient

from .client import get_toolforge_client
from .gen.toolforge_models import JobsJobResponse, JobsNewJob
from .models.api_models import Deployment, RunInfo, ToolConfig
from .settings import get_settings

logger = getLogger(__name__)


async def do_deploy(
    tool_name: str,
    tool_config: ToolConfig,
    deployment: Deployment,
) -> None:
    toolforge_client = get_toolforge_client()
    for component_name, component_info in tool_config.components.items():
        # TODO: add support to load all the components jobs and then sync the current status
        if component_info.component_type == "continuous":
            await deploy_continuous_jobs(
                tool_name=tool_name,
                run_info=component_info.run,
                component_name=component_name,
                image_name=component_info.build.use_prebuilt,
                toolforge_client=toolforge_client,
            )


async def deploy_continuous_jobs(
    tool_name: str,
    component_name: str,
    run_info: RunInfo,
    image_name: str,
    toolforge_client: ToolforgeAsyncClient,
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
        await toolforge_client.post(
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
