import time
import traceback
from copy import deepcopy
from datetime import datetime
from functools import partial, wraps
from logging import getLogger
from typing import Protocol, cast

from fastapi import HTTPException
from requests import HTTPError
from toolforge_weld.api_client import ToolforgeClient

from components.storage.base import Storage

from .client import get_toolforge_client
from .gen.toolforge_models import JobsJobResponse, JobsNewJob
from .models.api_models import (
    ComponentInfo,
    Deployment,
    DeploymentBuildInfo,
    DeploymentBuildState,
    DeploymentState,
    PrebuiltBuildInfo,
    RunInfo,
    SourceBuildInfo,
    ToolConfig,
)
from .settings import get_settings

logger = getLogger(__name__)


class DeployException(Exception):
    pass


class BuildFailed(DeployException):
    pass


class RunFailed(DeployException):
    pass


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


class DoDeployFuncType(Protocol):
    def __call__(
        self,
        *,
        tool_name: str,
        tool_config: ToolConfig,
        deployment: Deployment,
        storage: Storage,
    ) -> None: ...


class UpdateBuildInfoFuncType(Protocol):
    def __call__(self, *, build_info: dict[str, DeploymentBuildInfo]) -> None: ...


def set_deployment_as_failed_on_error(func: DoDeployFuncType) -> DoDeployFuncType:
    """Wraps the function in a try-except and sets the deployment status to error if any exception is raised.

    Very specific for do_deploy, but if needed could be generalized for others.
    """

    @wraps(func)
    def _inner(
        tool_name: str,
        tool_config: ToolConfig,
        deployment: Deployment,
        storage: Storage,
    ) -> None:
        try:
            return func(
                tool_name=tool_name,
                tool_config=tool_config,
                deployment=deployment,
                storage=storage,
            )
        except Exception as error:
            deployment.status = DeploymentState.failed
            deployment.long_status = f"Got exception: {error}\n{traceback.format_exc()}"
            _update_deployment(
                storage=storage, tool_name=tool_name, deployment=deployment
            )
            logger.exception(f"Deployment {deployment} failed: {error}")

    return _inner


def _update_deployment(
    storage: Storage, tool_name: str, deployment: Deployment
) -> None:
    """Thin wrapper on storage to add the http exception for the task."""
    try:
        storage.update_deployment(tool_name=tool_name, deployment=deployment)
        logger.info(f"Updated deployment {deployment} for tool {tool_name}")
    except Exception as error:
        logger.error(
            f"Error updating deployment {deployment} for tool {tool_name}: {error}"
        )
        raise HTTPException(status_code=500, detail=str(error)) from error


def _update_deployment_build_info(
    deployment: Deployment,
    build_info: dict[str, DeploymentBuildInfo],
    storage: Storage,
    tool_name: str,
) -> None:
    deployment.builds = build_info
    _update_deployment(deployment=deployment, storage=storage, tool_name=tool_name)


def _start_build(build: SourceBuildInfo, tool_name: str) -> DeploymentBuildInfo:
    toolforge_client = get_toolforge_client()
    build_data = {
        "ref": build.ref,
        "source_url": build.repository,
    }
    response = toolforge_client.post(
        f"/builds/v1/tool/{tool_name}/builds",
        json=build_data,
        verify=get_settings().verify_toolforge_api_cert,
    )

    return DeploymentBuildInfo(
        build_id=response["new_build"]["name"],
        build_status=DeploymentBuildState.pending,
    )


def _get_build_status(
    build: DeploymentBuildInfo, tool_name: str
) -> DeploymentBuildState:
    toolforge_client = get_toolforge_client()
    response = None
    unknown_error_message = ""
    try:
        response = toolforge_client.get(
            f"/builds/v1/tool/{tool_name}/builds/{build.build_id}",
            verify=get_settings().verify_toolforge_api_cert,
        )
    except HTTPError as error:
        if error.response.status_code == 404:
            logger.exception(
                f"Got 404 trying to fetch build status for tool {tool_name}, "
                f"build_id {build.build_id}, maybe someone deleted the build?: "
                "\n{traceback.format_exc()}"
            )
            return DeploymentBuildState.failed

        unknown_error_message = traceback.format_exc()

    except Exception:
        unknown_error_message = traceback.format_exc()

    if unknown_error_message or not response:
        logger.exception(
            f"Got error trying to fetch build status for tool {tool_name}, "
            f"build_id {build.build_id}: \n{unknown_error_message}"
        )
        return DeploymentBuildState.unknown

    if response["build"]["status"] == "BUILD_RUNNING":
        return DeploymentBuildState.running
    elif response["build"]["status"] == "BUILD_SUCCESS":
        return DeploymentBuildState.successful
    elif response["build"]["status"] in (
        "BUILD_FAILURE",
        "BUILD_CANCELLED",
        "BUILD_CANCELLED",
    ):
        return DeploymentBuildState.failed

    return DeploymentBuildState.unknown


def _wait_for_builds(
    builds: dict[str, DeploymentBuildInfo],
    update_build_info_func: UpdateBuildInfoFuncType,
    tool_name: str,
) -> None:
    settings = get_settings()
    pending_builds = {
        component: build
        for component, build in deepcopy(builds).items()
        if build.build_id
        not in (DeploymentBuildInfo.NO_ID_NEEDED, DeploymentBuildInfo.NO_ID_YET)
    }
    logger.debug(f"Waiting for {len(pending_builds)} builds to finish... from {builds}")

    start_time = datetime.now()
    while (
        pending_builds
        and (datetime.now() - start_time).seconds < settings.build_timeout_seconds
    ):
        to_delete = []
        for component_name, build in pending_builds.items():
            prev_build_status = builds[component_name].build_status
            builds[component_name] = DeploymentBuildInfo(
                build_id=build.build_id,
                build_status=_get_build_status(build=build, tool_name=tool_name),
            )
            # This saves some storage saving if the build status didn't change
            if prev_build_status != builds[component_name].build_status:
                update_build_info_func(build_info=builds)

            if builds[component_name].build_status in (
                DeploymentBuildState.successful,
                DeploymentBuildState.failed,
            ):
                to_delete.append(component_name)

        for component_name in to_delete:
            del pending_builds[component_name]
            logger.debug(
                f"Build for {component_name} finished, removing from list, {len(pending_builds)} builds left."
            )
        # Builds currently take in the order of minutes to complete, 2 seconds seems like often enough not to
        # overwhelm the api and still get a quick response once the build is finished.
        time.sleep(2)

    if pending_builds:
        raise BuildFailed(
            f"Some builds took too long to finish: {' '.join(pending_builds.keys())}"
        )

    failed_builds = [
        f"{component}(id:{build.build_id})"
        for component, build in builds.items()
        if build.build_status == DeploymentBuildState.failed
    ]
    if failed_builds:
        raise BuildFailed(
            f"Some builds failed, you can check the build logs for more info: {' '.join(failed_builds)}"
        )


def _start_builds(
    components: dict[str, ComponentInfo],
    update_build_info_func: UpdateBuildInfoFuncType,
    tool_name: str,
) -> dict[str, DeploymentBuildInfo]:
    any_failed = False
    failed_builds = []
    all_builds: dict[str, DeploymentBuildInfo] = {}
    for component_name, component in components.items():
        if isinstance(component.build, SourceBuildInfo):
            try:
                new_build_info = _start_build(
                    build=component.build, tool_name=tool_name
                )
            except Exception as error:
                any_failed = True
                new_build_info = DeploymentBuildInfo(
                    build_id=DeploymentBuildInfo.NO_ID_YET,
                    build_status=DeploymentBuildState.failed,
                )
                failed_builds.append(f"{component_name}(error:{error})")
        else:
            new_build_info = DeploymentBuildInfo(
                build_id=DeploymentBuildInfo.NO_ID_NEEDED,
                build_status=DeploymentBuildState.successful,
            )

        all_builds[component_name] = new_build_info

    update_build_info_func(build_info=all_builds)
    if any_failed:
        raise BuildFailed(f"Some builds failed to start: {' '.join(failed_builds)}")

    return all_builds


def _do_build(
    components: dict[str, ComponentInfo],
    update_build_info_func: UpdateBuildInfoFuncType,
    tool_name: str,
) -> None:
    logger.debug(f"Starting builds for tool {tool_name}")
    all_builds = _start_builds(
        components=components,
        update_build_info_func=update_build_info_func,
        tool_name=tool_name,
    )
    logger.debug(f"Waiting for builds to complete for tool {tool_name}")
    _wait_for_builds(
        builds=all_builds,
        update_build_info_func=update_build_info_func,
        tool_name=tool_name,
    )
    logger.debug(f"Builds done for tool {tool_name}")


@set_deployment_as_failed_on_error
def do_deploy(
    *,
    tool_name: str,
    tool_config: ToolConfig,
    deployment: Deployment,
    storage: Storage,
) -> None:
    logger.info(f"Starting deployment for tool {tool_name}")

    deployment.status = DeploymentState.running
    deployment.long_status = f"Started at {datetime.now()}"
    _update_deployment(storage=storage, tool_name=tool_name, deployment=deployment)

    _update_build_info_func = partial(
        _update_deployment_build_info,
        storage=storage,
        tool_name=tool_name,
        deployment=deployment,
    )
    _do_build(
        components=tool_config.components,
        update_build_info_func=_update_build_info_func,
        tool_name=tool_name,
    )

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
        try:
            run_continuous_jobs(
                tool_name=tool_name,
                run_info=component_info.run,
                component_name=component_name,
                image_name=_get_component_image_name(
                    tool_name=tool_name, component_info=component_info
                ),
                toolforge_client=toolforge_client,
            )
        except Exception as error:
            raise RunFailed(f"Failed to run some components: {error}") from error

        deployment.status = DeploymentState.successful
        deployment.long_status = f"Finished at {datetime.now()}"
        _update_deployment(storage=storage, tool_name=tool_name, deployment=deployment)

        # TODO: check if the components are actually running ok


def run_continuous_jobs(
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
    # TODO: check if the job is actually running ok


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
        timeout=None,
    )
