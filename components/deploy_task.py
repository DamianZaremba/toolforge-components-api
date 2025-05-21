import subprocess
import time
import traceback
from copy import deepcopy
from datetime import datetime, timezone
from functools import partial, wraps
from logging import getLogger
from typing import Protocol

from fastapi import HTTPException, status
from requests import HTTPError
from toolforge_weld.api_client import ToolforgeClient

from components.storage.base import Storage

from .client import get_toolforge_client
from .gen.toolforge_models import (
    BuildsBuild,
    BuildsBuildParameters,
    BuildsBuildStatus,
    BuildsListResponse,
    JobsJobResponse,
    JobsNewJob,
)
from .models.api_models import (
    ComponentInfo,
    Deployment,
    DeploymentBuildInfo,
    DeploymentBuildState,
    DeploymentRunInfo,
    DeploymentRunState,
    DeploymentState,
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


def _get_component_image_name(
    component_info: ComponentInfo,
    component_name: str,
) -> str:
    match component_info.build:
        case SourceBuildInfo():
            logger.debug(f"Got source build type: {component_info}")
            # TODO: use the actual build logs/info to get the image name once we trigger builds
            # The tag and the prefix are currently added by builds-api during build
            return component_name

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

            for run in deployment.runs.values():
                if run.run_status == DeploymentRunState.pending:
                    run.run_status = DeploymentRunState.skipped
                    run.run_long_status = "Skipped due to previous failure"

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


def _resolve_ref(build_info: SourceBuildInfo) -> str:
    source_url = build_info.repository
    ref = build_info.ref
    if not ref:
        ref = "HEAD"

    logger.debug(f"Resolving ref '{ref}' for git repository '{source_url}'")
    result = subprocess.run(
        ["git", "ls-remote", source_url, ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        logger.exception(
            f"Got error trying to resolve ref '{ref}' for repository '{source_url}'. Error: {result.stderr}"
        )
        return ""

    parts = result.stdout.split()
    if parts:
        logger.debug(
            f"Resolved ref '{ref}' for repository '{source_url}' to commit hash '{parts[0]}'"
        )
        return parts[0]

    logger.exception(
        f"Failed to resolve ref '{ref}' for repository '{source_url}'. Got: {result.stdout}"
    )
    return ""


def _check_for_matching_build(
    component_name: str, build_info: SourceBuildInfo, tool_name: str
) -> BuildsBuild | None:
    matching_build: BuildsBuild | None = None
    toolforge_client = get_toolforge_client()

    response = toolforge_client.get(
        f"/builds/v1/tool/{tool_name}/builds",
        verify=get_settings().verify_toolforge_api_cert,
    )

    builds = BuildsListResponse.model_validate(response).builds
    if not builds:
        return None

    builds = sorted(
        builds,
        key=lambda build: (
            build.start_time
            if build.start_time
            else datetime.min.replace(tzinfo=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        ),
        reverse=True,
    )
    logger.debug(
        f"Found {len(builds)} builds for tool {tool_name} to compare for skipping"
    )
    for build in builds:
        image_name = (
            build.destination_image
            and build.destination_image.split("/")[-1].split(":")[0]
        )
        if image_name == component_name:
            matching_build = build
            break

    if not matching_build:
        return None

    build_info_ref = _resolve_ref(build_info)
    if matching_build.resolved_ref == build_info_ref:
        logger.debug(f"Gotten matching build: {matching_build.model_dump()}")
        return matching_build

    return None


def _start_build(
    build: SourceBuildInfo,
    tool_name: str,
    component_name: str,
) -> DeploymentBuildInfo:
    toolforge_client = get_toolforge_client()
    build_data = BuildsBuildParameters(
        ref=build.ref,
        source_url=build.repository,
        image_name=component_name,
        envvars={},
        # TODO: pull from the config
        use_latest_versions=False,
    )

    matching_build = _check_for_matching_build(
        component_name=component_name, build_info=build, tool_name=tool_name
    )
    if matching_build and matching_build.status == BuildsBuildStatus.BUILD_SUCCESS:
        logger.debug(
            f"A successful matching build '{matching_build.build_id}' for component '{component_name}' was found."
            "Skipping build and marking deployment as skipped ..."
        )
        if not matching_build.build_id:
            raise Exception(f"Unexpected build without id: {matching_build}")
        return DeploymentBuildInfo(
            build_id=matching_build.build_id,
            build_status=DeploymentBuildState.skipped,
        )

    if matching_build and matching_build.status in (
        BuildsBuildStatus.BUILD_PENDING,
        BuildsBuildStatus.BUILD_RUNNING,
    ):
        logger.debug(
            f"A pending matching build '{matching_build.build_id}' for component '{component_name}' was found."
            "Skipping build and marking deployment as pending ..."
        )
        if not matching_build.build_id:
            raise Exception(f"Unexpected build without id: {matching_build}")
        return DeploymentBuildInfo(
            build_id=matching_build.build_id,
            build_status=DeploymentBuildState.pending,
        )

    response = toolforge_client.post(
        f"/builds/v1/tool/{tool_name}/builds",
        json=build_data.model_dump(),
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
        if error.response.status_code == status.HTTP_404_NOT_FOUND:
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

    response_status = BuildsBuildStatus(response["build"]["status"])
    if response_status == BuildsBuildStatus.BUILD_RUNNING:
        return DeploymentBuildState.running
    elif response_status == BuildsBuildStatus.BUILD_SUCCESS:
        return DeploymentBuildState.successful
    elif response_status in (
        BuildsBuildStatus.BUILD_FAILURE,
        BuildsBuildStatus.BUILD_CANCELLED,
        BuildsBuildStatus.BUILD_TIMEOUT,
    ):
        return DeploymentBuildState.failed

    return DeploymentBuildState.unknown


def _wait_for_builds(
    builds: dict[str, DeploymentBuildInfo],
    update_build_info_func: UpdateBuildInfoFuncType,
    tool_name: str,
) -> None:
    settings = get_settings()
    pending_builds: dict[str, DeploymentBuildInfo] = {
        component: deepcopy(build)
        for component, build in builds.items()
        if build.build_status
        in (
            DeploymentBuildState.pending,
            DeploymentBuildState.running,
        )
    }
    logger.debug(f"Waiting for {len(pending_builds)} builds to finish... from {builds}")

    start_time = datetime.now()
    while (
        pending_builds
        and (datetime.now() - start_time).total_seconds()
        < settings.build_timeout_seconds
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
                    build=component.build,
                    tool_name=tool_name,
                    component_name=component_name,
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
                build_id=DeploymentBuildInfo.NO_BUILD_NEEDED,
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


def _do_run(
    components: dict[str, ComponentInfo],
    tool_name: str,
    deployment: Deployment,
    storage: Storage,
) -> None:
    toolforge_client = get_toolforge_client()
    for component_name, component_info in components.items():
        run_info = DeploymentRunInfo(run_status=DeploymentRunState.pending)
        deployment.runs[component_name] = run_info
        _update_deployment(storage=storage, tool_name=tool_name, deployment=deployment)

        # TODO: add support to load all the components jobs and then sync the current status
        if component_info.component_type != "continuous":
            logger.info(
                f"{tool_name}: skipping component {component_name} (non continuous is not supported yet)"
            )
            run_info = DeploymentRunInfo(run_status=DeploymentRunState.skipped)
            deployment.runs[component_name] = run_info
            _update_deployment(
                storage=storage, tool_name=tool_name, deployment=deployment
            )
            continue

        logger.info(
            f"{tool_name}: deploying component {component_name}: {component_info}"
        )
        has_error = True
        message = "Unknown error"
        try:
            message = run_continuous_jobs(
                tool_name=tool_name,
                run_info=component_info.run,
                component_name=component_name,
                image_name=f"tool-{tool_name}/"
                + _get_component_image_name(
                    component_info=component_info,
                    component_name=component_name,
                )
                + ":latest",
                toolforge_client=toolforge_client,
            )
            has_error = False

        except HTTPError as error:
            message = f"{error} ({error.response.status_code}): "
            try:
                message += ", ".join(error.response.json().get("error", ["no details"]))
            except Exception as parse_error:
                logger.error(
                    f"Failed parsing error response from jobs api {parse_error}, response:\n{error.response}"
                )
                message += f"failed to parse error {parse_error}"
                pass
            has_error = True

        except Exception as error:
            message = str(error)
            has_error = True

        if has_error:
            run_info = DeploymentRunInfo(
                run_status=DeploymentRunState.failed, run_long_status=message
            )
            deployment.runs[component_name] = run_info
            _update_deployment(
                storage=storage, tool_name=tool_name, deployment=deployment
            )
            raise RunFailed(f"Failed run for component {component_name}: {message}")

        deployment.status = DeploymentState.successful
        deployment.long_status = f"Finished at {datetime.now()}"
        # TODO: check if the components are actually running ok
        run_info = DeploymentRunInfo(
            run_status=DeploymentRunState.successful, run_long_status=message
        )
        deployment.runs[component_name] = run_info
        _update_deployment(storage=storage, tool_name=tool_name, deployment=deployment)


def run_continuous_jobs(
    tool_name: str,
    component_name: str,
    run_info: RunInfo,
    image_name: str,
    toolforge_client: ToolforgeClient,
) -> str:
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
    # Using patch here does an upsert
    create_response = JobsJobResponse.model_validate(
        toolforge_client.patch(
            f"/jobs/v1/tool/{tool_name}/jobs/",
            json=new_job.model_dump(mode="json", exclude_none=True),
            verify=settings.verify_toolforge_api_cert,
        )
    )
    logger.debug(f"Deployed continuous job {component_name}: {create_response}")
    # TODO: check if the job is actually running ok
    if create_response.job:
        return f"created continuous job {create_response.job.name}"

    elif not create_response.messages:
        return f"unable to get job info, response from jobs api {create_response}"

    else:
        message = ""
        for level, messages in create_response.messages:
            if messages:
                message += f"[{level}] ({', '.join(messages)})"
        return message


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
    _do_run(
        components=tool_config.components,
        tool_name=tool_name,
        deployment=deployment,
        storage=storage,
    )
