import datetime
import subprocess
from logging import getLogger
from typing import TypeAlias

from fastapi import status
from requests import HTTPError

from ..client import get_toolforge_client
from ..exceptions import BuildFailed
from ..gen.toolforge_models import (
    BuildsBuild,
    BuildsBuildParameters,
    BuildsBuildStatus,
    BuildsListResponse,
    JobsHttpHealthCheck,
    JobsJobListResponse,
    JobsJobResponse,
    JobsNewContinuousJob,
    JobsNewOneOffJob,
    JobsNewScheduledJob,
    JobsResponseMessages,
    JobsScriptHealthCheck,
)
from ..models.api_models import (
    ComponentInfo,
    ContinuousRunInfo,
    DeploymentBuildInfo,
    DeploymentBuildState,
    ScheduledRunInfo,
    SourceBuildInfo,
)
from ..settings import get_settings
from .base import AnyDefinedJob, Runtime

logger = getLogger(__name__)


AnyNewJob: TypeAlias = JobsNewContinuousJob | JobsNewOneOffJob | JobsNewScheduledJob


def _resolve_ref(build_info: SourceBuildInfo) -> str:
    source_url = build_info.repository.encoded_string()
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
        logger.error(
            f"Got error trying to resolve ref '{ref}' for repository '{source_url}'. Error: {result.stderr}"
        )
        return ""

    parts = result.stdout.split()
    if parts:
        logger.debug(
            f"Resolved ref '{ref}' for repository '{source_url}' to commit hash '{parts[0]}'"
        )
        return parts[0]

    message = (
        f"Failed to resolve ref '{ref}' for repository '{source_url}', does it exist?"
    )
    logger.error(f"{message} Got: {result.stdout}")
    raise BuildFailed(message)


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
            else datetime.datetime.min.replace(tzinfo=datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        ),
        reverse=True,
    )
    logger.debug(
        f"Found {len(builds)} builds for tool {tool_name} to compare for skipping"
    )

    for build in builds:
        if build.parameters and build.parameters.image_name == component_name:
            matching_build = build
            break

    if not matching_build:
        return None

    if not matching_build.parameters and build_info.use_latest_versions:
        return None
    elif matching_build.parameters:
        if (
            matching_build.parameters.use_latest_versions
            != build_info.use_latest_versions
        ):
            return None

    build_info_ref = _resolve_ref(build_info)
    if matching_build.resolved_ref == build_info_ref:
        logger.debug(f"Gotten matching build: {matching_build.model_dump()}")
        return matching_build

    return None


def _run_info_to_continuous_job(
    component_name: str, run_info: ContinuousRunInfo, image_name: str
) -> AnyNewJob:
    # TODO: the generator seems to make every parameter mandatory :/, try to fix that somehow

    run_info_data = run_info.model_dump(exclude_unset=True)
    health_check: JobsHttpHealthCheck | JobsScriptHealthCheck | None = None
    if run_info_data.get("health_check_http", None):
        health_check = JobsHttpHealthCheck(
            type="http", path=run_info_data["health_check_http"]
        )
    elif run_info_data.get("health_check_script", None):
        health_check = JobsScriptHealthCheck(
            type="script",
            script=run_info_data["health_check_script"],
        )
    params = {
        # we always want to send job_type
        "job_type": "continuous",
        "cmd": run_info_data["command"],
        "name": component_name,
        "imagename": image_name,
    }
    if health_check:
        params["health_check"] = health_check.model_dump()

    for field in [
        "cpu",
        "memory",
        "filelog",
        "filelog_stderr",
        "filelog_stdout",
        "replicas",
        "mount",
        "port",
        "port_protocol",
        "emails",
    ]:
        if field in run_info_data:
            params[field] = run_info_data[field]

    return JobsNewContinuousJob.model_validate(params)


def _run_info_to_scheduled_job(
    component_name: str, run_info: ScheduledRunInfo, image_name: str
) -> AnyNewJob:
    run_info_data = run_info.model_dump(exclude_unset=True)
    params = {
        # we always want to send job_type
        "job_type": "scheduled",
        "cmd": run_info_data["command"],
        "name": component_name,
        "imagename": image_name,
        "schedule": run_info_data["schedule"],
    }
    for field in [
        "cpu",
        "memory",
        "filelog",
        "filelog_stderr",
        "filelog_stdout",
        "mount",
        "emails",
        "timeout",
        "retry",
    ]:
        if field in run_info_data:
            params[field] = run_info_data[field]

    return JobsNewScheduledJob.model_validate(params)


class ToolforgeRuntime(Runtime):
    def get_build_info(
        self, build: DeploymentBuildInfo, tool_name: str
    ) -> DeploymentBuildInfo:
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
                    f"build_id {build.build_id}, maybe someone deleted the build?"
                )
                return DeploymentBuildInfo(
                    build_id=build.build_id,
                    build_status=DeploymentBuildState.failed,
                    build_long_status=f"build {build.build_id} not found, maybe it was deleted?",
                )

            logger.exception(
                f"Got {error} trying to fetch build status for tool {tool_name}, "
                f"build_id {build.build_id}"
            )
            unknown_error_message = f"Unknown HTTP error {error}"

        except Exception as error:
            logger.exception(
                f"Got {error} trying to fetch build status for tool {tool_name}, "
                f"build_id {build.build_id}"
            )
            unknown_error_message = f"Unknown error {error}"

        if unknown_error_message or not response:
            logger.error(
                f"Got error trying to fetch build status for tool {tool_name}, "
                f"build_id {build.build_id}: \n{unknown_error_message}"
            )
            return DeploymentBuildInfo(
                build_id=build.build_id,
                build_status=DeploymentBuildState.unknown,
                build_long_status=unknown_error_message or "got empty response",
            )

        response_status = BuildsBuildStatus(response["build"]["status"])
        if response_status == BuildsBuildStatus.BUILD_RUNNING:
            deployment_build_state, build_long_status = (
                DeploymentBuildState.running,
                f"You can see the logs with `toolforge build logs {build.build_id}`",
            )
        elif response_status == BuildsBuildStatus.BUILD_SUCCESS:
            deployment_build_state, build_long_status = (
                DeploymentBuildState.successful,
                f"You can see the logs with `toolforge build logs {build.build_id}`",
            )
        elif response_status in (
            BuildsBuildStatus.BUILD_FAILURE,
            BuildsBuildStatus.BUILD_CANCELLED,
            BuildsBuildStatus.BUILD_TIMEOUT,
        ):
            deployment_build_state, build_long_status = (
                DeploymentBuildState.failed,
                f"You can see the logs with `toolforge build logs {build.build_id}`",
            )
        else:
            deployment_build_state, build_long_status = (
                DeploymentBuildState.unknown,
                f"You can see the logs with `toolforge build logs {build.build_id}`",
            )

        return DeploymentBuildInfo(
            build_id=build.build_id,
            build_status=deployment_build_state,
            build_image=response["build"].get(
                "destination_image", DeploymentBuildInfo.NO_IMAGE_YET
            ),
            build_long_status=build_long_status,
        )

    def start_build(
        self,
        build: SourceBuildInfo,
        tool_name: str,
        component_name: str,
        component_info: ComponentInfo,
        force_build: bool,
    ) -> DeploymentBuildInfo:
        toolforge_client = get_toolforge_client()
        if not force_build:
            matching_build = _check_for_matching_build(
                component_name=component_name, build_info=build, tool_name=tool_name
            )
            if (
                matching_build
                and matching_build.status == BuildsBuildStatus.BUILD_SUCCESS
            ):
                logger.debug(
                    f"A successful matching build '{matching_build.build_id}' for component '{component_name}' was found."
                    "Skipping build and marking deployment as skipped ..."
                )
                if not matching_build.build_id:
                    raise Exception(f"Unexpected build without id: {matching_build}")
                if not matching_build.destination_image:
                    raise Exception(
                        f"Unexpected build without destination image: {matching_build}"
                    )
                return DeploymentBuildInfo(
                    build_id=matching_build.build_id,
                    build_status=DeploymentBuildState.skipped,
                    build_long_status="Reusing existing build",
                    build_image=matching_build.destination_image,
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
                    build_long_status="Not started yet",
                )

        build_data = BuildsBuildParameters(
            ref=build.ref,
            source_url=build.repository.encoded_string(),
            image_name=component_name,
            envvars={},
            use_latest_versions=build.use_latest_versions,
        )
        response = toolforge_client.post(
            f"/builds/v1/tool/{tool_name}/builds",
            json=build_data.model_dump(exclude_unset=True),
            verify=get_settings().verify_toolforge_api_cert,
        )

        return DeploymentBuildInfo(
            build_id=response["new_build"]["name"],
            build_status=DeploymentBuildState.pending,
            build_long_status="Not started yet",
        )

    def _format_status_messages(
        self, base_message: str, api_messages: JobsResponseMessages | None
    ) -> str:
        message = base_message
        if api_messages:
            for level, level_messages in api_messages:
                if level_messages:
                    message += f", [{level}]({', '.join(level_messages)})"
        return message

    def run_continuous_job(
        self,
        tool_name: str,
        component_name: str,
        component_info: ComponentInfo,
        force_restart: bool,
        image_name: str,
    ) -> str:
        if not isinstance(component_info.run, ContinuousRunInfo):
            raise ValueError(
                f"Invalid run info passed, it's not a ContinuousRunInfo: {component_info.run}"
            )
        settings = get_settings()
        toolforge_client = get_toolforge_client()

        # TODO: delete all the other jobs that we don't manage
        logger.debug(
            f"Creating job for component {component_name} with image {image_name} and run_info {component_info.run}"
        )
        new_job = _run_info_to_continuous_job(
            component_name=component_name,
            run_info=component_info.run,
            image_name=image_name,
        )

        # always send job_type
        new_job.model_fields_set.add("job_type")
        json_data = new_job.model_dump(
            mode="json",
            exclude_unset=True,
        )
        logger.debug(f"Sending job info {json_data} to jobs-api")
        # Using patch here does an upsert
        create_response = JobsJobResponse.model_validate(
            toolforge_client.patch(
                f"/jobs/v1/tool/{tool_name}/jobs/",
                json=json_data,
                verify=settings.verify_toolforge_api_cert,
            )
        )
        logger.debug(f"Deployed continuous job {component_name}: {create_response}")
        if create_response.job_changed:
            # TODO: check if the job is actually running ok
            return self._format_status_messages(
                f"created or updated job {component_name}", create_response.messages
            )

        elif force_restart:
            logger.debug(
                f"Explicitly restarting continuous job {component_name} as the configuration did not change"
            )
            toolforge_client.post(
                f"/jobs/v1/tool/{tool_name}/jobs/{component_name}/restart/",
                verify=settings.verify_toolforge_api_cert,
            )
            return self._format_status_messages(
                f"restarted job {component_name}", create_response.messages
            )

        else:
            return self._format_status_messages(
                f"job {component_name} is already up to date", create_response.messages
            )

    def run_scheduled_job(
        self,
        tool_name: str,
        component_name: str,
        component_info: ComponentInfo,
        image_name: str,
    ) -> str:
        if not isinstance(component_info.run, ScheduledRunInfo):
            raise ValueError(
                f"Invalid run info passed, it's not a ScheduledRunInfo: {component_info.run}"
            )
        settings = get_settings()
        toolforge_client = get_toolforge_client()

        # TODO: delete all the other jobs that we don't manage
        logger.debug(
            f"Creating job for component {component_name} with image {image_name} and run_info {component_info.run}"
        )
        new_job = _run_info_to_scheduled_job(
            component_name=component_name,
            run_info=component_info.run,
            image_name=image_name,
        )
        json_data = new_job.model_dump(mode="json", exclude_unset=True)
        logger.debug(f"Sending job info {json_data} to jobs-api")
        # Using patch here does an upsert
        create_response = JobsJobResponse.model_validate(
            toolforge_client.patch(
                f"/jobs/v1/tool/{tool_name}/jobs/",
                json=json_data,
                verify=settings.verify_toolforge_api_cert,
            )
        )
        logger.debug(f"Deployed scheduled job {component_name}: {create_response}")
        if create_response.job_changed:
            return self._format_status_messages(
                f"created or updated job {component_name}", create_response.messages
            )
        else:
            return self._format_status_messages(
                f"job {component_name} is already up to date", create_response.messages
            )

    def delete_job_if_exists(
        self,
        tool_name: str,
        component_name: str,
    ) -> str:
        message = ""
        settings = get_settings()
        toolforge_client = get_toolforge_client()
        logger.debug(f"Getting jobs for tool {tool_name}")
        jobs = JobsJobListResponse.model_validate(
            toolforge_client.get(
                f"/jobs/v1/tool/{tool_name}/jobs",
                verify=settings.verify_toolforge_api_cert,
            )
        ).jobs

        if not jobs or not any([job.name == component_name for job in jobs]):
            logger.debug(
                f"Job {component_name} not found for tool {tool_name}. Skipping delete operation..."
            )
            return message

        logger.debug(f"Deleting job {component_name} for tool {tool_name}")
        delete_response = JobsJobResponse.model_validate(
            toolforge_client.delete(
                f"/jobs/v1/tool/{tool_name}/jobs/{component_name}",
                verify=settings.verify_toolforge_api_cert,
            )
        )
        logger.debug(
            f"Deleted continuous job {component_name} for tool {tool_name}: {delete_response}"
        )
        if not delete_response.messages:
            return message

        for level, messages in delete_response.messages:
            if messages:
                message += f"[{level}] ({', '.join(messages)})"
        return message

    def get_jobs(self, tool_name: str) -> list[AnyDefinedJob]:
        toolforge_client = get_toolforge_client()
        raw_response = toolforge_client.get(
            f"/jobs/v1/tool/{tool_name}/jobs",
            verify=get_settings().verify_toolforge_api_cert,
            params={"include_unset": False},
        )
        parsed_response = JobsJobListResponse.model_validate(raw_response)
        return parsed_response.jobs or []

    def get_builds(self, tool_name: str) -> list[BuildsBuild]:
        toolforge_client = get_toolforge_client()
        raw_response = toolforge_client.get(
            f"/builds/v1/tool/{tool_name}/builds",
            verify=get_settings().verify_toolforge_api_cert,
        )
        parsed_response = BuildsListResponse.model_validate(raw_response)
        return parsed_response.builds or []

    def cancel_build(self, tool_name: str, build_id: str) -> None:
        toolforge_client = get_toolforge_client()
        toolforge_client.put(
            f"/builds/v1/tool/{tool_name}/builds/{build_id}/cancel",
            verify=get_settings().verify_toolforge_api_cert,
        )
