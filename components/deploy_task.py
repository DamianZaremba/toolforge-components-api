import time
import traceback
from copy import deepcopy
from datetime import datetime
from functools import partial, wraps
from logging import getLogger
from typing import Protocol

from fastapi import HTTPException, status
from requests import HTTPError

from .exceptions import BuildFailed, RunFailed
from .models.api_models import (
    ComponentInfo,
    Deployment,
    DeploymentBuildInfo,
    DeploymentBuildState,
    DeploymentRunInfo,
    DeploymentRunState,
    DeploymentState,
    SourceBuildInfo,
    ToolConfig,
)
from .runtime.base import Runtime
from .settings import get_settings
from .storage.base import Storage

logger = getLogger(__name__)


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
        runtime: Runtime,
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
        runtime: Runtime,
    ) -> None:
        try:
            return func(
                tool_name=tool_name,
                tool_config=tool_config,
                deployment=deployment,
                storage=storage,
                runtime=runtime,
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


def _wait_for_builds(
    builds: dict[str, DeploymentBuildInfo],
    update_build_info_func: UpdateBuildInfoFuncType,
    tool_name: str,
    runtime: Runtime,
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
            build_status, build_long_status = runtime.get_build_statuses(
                build=build, tool_name=tool_name
            )
            builds[component_name] = DeploymentBuildInfo(
                build_id=build.build_id,
                build_status=build_status,
                build_long_status=build_long_status,
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


def _parse_build_error(error: Exception) -> str:
    message = f"unexpected {error}"
    logger.debug(f"Parsing build error {error}")
    match error:
        case BuildFailed():
            logger.debug(f"Got BuildFailed: {error}")
            message = f"{error}"
        case HTTPError():
            if (
                status.HTTP_400_BAD_REQUEST
                <= (error.response.status_code or 0)
                <= status.HTTP_500_INTERNAL_SERVER_ERROR
            ):
                try:
                    logger.debug(f"Got 4xx HTTPError: {error}")
                    message = ", ".join(error.response.json()["error"])
                except Exception:
                    logger.debug(f"Got non-json 4xx HTTPError: {error}")
                    message = f"unexpected {error}: {error.response.text}"
            else:
                logger.debug(f"Got unexpected HTTPError {error}:{error.response.text}")
        case _:
            logger.debug(f"Got unexpected non-HTTPError: {error}")

    return message


def _start_builds(
    components: dict[str, ComponentInfo],
    update_build_info_func: UpdateBuildInfoFuncType,
    tool_name: str,
    runtime: Runtime,
    force_build: bool,
) -> dict[str, DeploymentBuildInfo]:
    any_failed = False
    failed_builds = []
    all_builds: dict[str, DeploymentBuildInfo] = {}
    logger.debug(f"Starting {len(components)} components builds")
    for component_name, component in components.items():
        logger.debug(f"Starting build for {component_name}")
        if isinstance(component.build, SourceBuildInfo):
            try:
                new_build_info = runtime.start_build(
                    build=component.build,
                    tool_name=tool_name,
                    component_name=component_name,
                    component_info=component,
                    force_build=force_build,
                )
                logger.debug(f"Build started {new_build_info}")
            except Exception as error:
                any_failed = True
                message = _parse_build_error(error=error)
                new_build_info = DeploymentBuildInfo(
                    # TODO: maybe change this field name, or stop using it for non-ids
                    build_id="no-id-yet",
                    build_status=DeploymentBuildState.failed,
                    build_long_status=message,
                )
                failed_builds.append(f"{component_name}(error:{error})")
                logger.debug(f"Build failed to start {new_build_info}")
        else:
            new_build_info = DeploymentBuildInfo(
                build_id=DeploymentBuildInfo.NO_BUILD_NEEDED,
                build_status=DeploymentBuildState.skipped,
                build_long_status="Not a build-service based job",
            )
            logger.debug("Skipping non-source build ")

        all_builds[component_name] = new_build_info

    update_build_info_func(build_info=all_builds)
    if any_failed:
        message = f"Some builds failed to start: {' '.join(failed_builds)}"
        logger.error(message)
        raise BuildFailed(message)

    return all_builds


def _do_build(
    components: dict[str, ComponentInfo],
    update_build_info_func: UpdateBuildInfoFuncType,
    tool_name: str,
    force_build: bool,
    runtime: Runtime,
) -> None:
    logger.debug(f"Starting builds for tool {tool_name}")
    all_builds = _start_builds(
        components=components,
        update_build_info_func=update_build_info_func,
        tool_name=tool_name,
        force_build=force_build,
        runtime=runtime,
    )
    logger.debug(f"Waiting for builds to complete for tool {tool_name}")
    _wait_for_builds(
        builds=all_builds,
        update_build_info_func=update_build_info_func,
        tool_name=tool_name,
        runtime=runtime,
    )
    logger.debug(f"Builds done for tool {tool_name}")


def _do_run(
    components: dict[str, ComponentInfo],
    tool_name: str,
    deployment: Deployment,
    storage: Storage,
    runtime: Runtime,
) -> None:
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
        needs_rerun = (
            deployment.force_run
            or deployment.builds[component_name].build_status
            == DeploymentBuildState.successful
        )
        try:
            if needs_rerun:
                # TODO: we might want to implement a more 'graceful' way of restarting a continuous job than deleting
                # and creating, to allow for example not needing te recreate the k8s service underneath forcing
                # a restart of any other jobs that might be using this one by name internally
                message = runtime.delete_continuous_job_if_exists(
                    tool_name=tool_name,
                    component_name=component_name,
                )

            message = runtime.run_continuous_job(
                tool_name=tool_name,
                component_info=component_info,
                component_name=component_name,
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
            logger.error(f"Unknown error response from jobs api {error!r}")
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


@set_deployment_as_failed_on_error
def do_deploy(
    *,
    tool_name: str,
    tool_config: ToolConfig,
    deployment: Deployment,
    storage: Storage,
    runtime: Runtime,
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
        force_build=deployment.force_build,
        runtime=runtime,
    )
    _do_run(
        components=tool_config.components,
        tool_name=tool_name,
        deployment=deployment,
        storage=storage,
        runtime=runtime,
    )
