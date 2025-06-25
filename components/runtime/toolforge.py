import datetime
import subprocess
import traceback
from logging import getLogger

from fastapi import status
from requests import HTTPError

from ..client import get_toolforge_client
from ..exceptions import BuildFailed
from ..gen.toolforge_models import (
    BuildsBuild,
    BuildsBuildParameters,
    BuildsBuildStatus,
    BuildsListResponse,
    JobsDefinedJob,
    JobsHttpHealthCheck,
    JobsJobListResponse,
    JobsJobResponse,
    JobsNewJob,
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
from .base import Runtime

logger = getLogger(__name__)


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


def _get_component_image_name(
    component_info: ComponentInfo, component_name: str
) -> str:
    match component_info.build:
        case SourceBuildInfo():
            logger.debug(f"Got source build type: {component_info}")
            # TODO: use the actual build logs/info to get the image name once we trigger builds
            # The tag and the prefix are currently added by builds-api during build
            return f"{component_name}"

    logger.error(f"Unsupported build information: {component_info.build}")
    raise Exception(f"unsupported build information: {component_info.build}")


def _run_info_to_continuous_job(
    component_name: str, run_info: ContinuousRunInfo, image_name: str
) -> JobsNewJob:
    # TODO: the generator seems to make every parameter mandatory :/, try to fix that somehow

    health_check: JobsHttpHealthCheck | JobsScriptHealthCheck | None = None
    if run_info.health_check_http:
        health_check = JobsHttpHealthCheck(type="http", path=run_info.health_check_http)
    elif run_info.health_check_script:
        health_check = JobsScriptHealthCheck(
            type="script",
            script=run_info.health_check_script,
        )

    return JobsNewJob(
        cmd=run_info.command,
        name=component_name,
        imagename=image_name,
        continuous=True,
        cpu=run_info.cpu,
        emails=run_info.emails,
        filelog=run_info.filelog,
        filelog_stderr=run_info.filelog_stderr,
        filelog_stdout=run_info.filelog_stdout,
        health_check=health_check,
        memory=run_info.memory,
        mount=run_info.mount,
        port=run_info.port,
        replicas=run_info.replicas,
        retry=None,
        schedule=None,
        timeout=None,
    )


def _run_info_to_scheduled_job(
    component_name: str, run_info: ScheduledRunInfo, image_name: str
) -> JobsNewJob:
    return JobsNewJob(
        cmd=run_info.command,
        name=component_name,
        imagename=image_name,
        continuous=False,
        cpu=run_info.cpu,
        emails=run_info.emails,
        filelog=run_info.filelog,
        filelog_stderr=run_info.filelog_stderr,
        filelog_stdout=run_info.filelog_stdout,
        health_check=None,
        memory=run_info.memory,
        mount=run_info.mount,
        port=None,
        replicas=None,
        retry=run_info.retry,
        schedule=run_info.schedule,
        timeout=run_info.timeout,
    )


class ToolforgeRuntime(Runtime):
    def get_build_statuses(
        self, build: DeploymentBuildInfo, tool_name: str
    ) -> tuple[DeploymentBuildState, str]:
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
                return (
                    DeploymentBuildState.failed,
                    f"build {build.build_id} not found, maybe it was deleted?",
                )

            unknown_error_message = traceback.format_exc()

        except Exception:
            unknown_error_message = traceback.format_exc()

        if unknown_error_message or not response:
            logger.error(
                f"Got error trying to fetch build status for tool {tool_name}, "
                f"build_id {build.build_id}: \n{unknown_error_message}"
            )
            return (
                DeploymentBuildState.unknown,
                unknown_error_message or "got empty response",
            )

        response_status = BuildsBuildStatus(response["build"]["status"])
        if response_status == BuildsBuildStatus.BUILD_RUNNING:
            return (
                DeploymentBuildState.running,
                f"You can see the logs with `toolforge build logs {build.build_id}`",
            )
        elif response_status == BuildsBuildStatus.BUILD_SUCCESS:
            return (
                DeploymentBuildState.successful,
                f"You can see the logs with `toolforge build logs {build.build_id}`",
            )
        elif response_status in (
            BuildsBuildStatus.BUILD_FAILURE,
            BuildsBuildStatus.BUILD_CANCELLED,
            BuildsBuildStatus.BUILD_TIMEOUT,
        ):
            return (
                DeploymentBuildState.failed,
                f"You can see the logs with `toolforge build logs {build.build_id}`",
            )

        return (
            DeploymentBuildState.unknown,
            f"You can see the logs with `toolforge build logs {build.build_id}`",
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
                return DeploymentBuildInfo(
                    build_id=matching_build.build_id,
                    build_status=DeploymentBuildState.skipped,
                    build_long_status="Reusing existing build",
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
            source_url=build.repository,
            image_name=_get_component_image_name(
                component_info=component_info,
                component_name=component_name,
            ),
            envvars={},
            # TODO: pull from the config
            use_latest_versions=False,
        )
        response = toolforge_client.post(
            f"/builds/v1/tool/{tool_name}/builds",
            json=build_data.model_dump(),
            verify=get_settings().verify_toolforge_api_cert,
        )

        return DeploymentBuildInfo(
            build_id=response["new_build"]["name"],
            build_status=DeploymentBuildState.pending,
            build_long_status="Not started yet",
        )

    def run_continuous_job(
        self,
        tool_name: str,
        component_name: str,
        component_info: ComponentInfo,
    ) -> str:
        if not isinstance(component_info.run, ContinuousRunInfo):
            raise ValueError(
                f"Invalid run info passed, it's not a ContinuousRunInfo: {component_info.run}"
            )
        # TODO: manage the tag in a nicer way overall
        image_name = (
            f"tool-{tool_name}/"
            + _get_component_image_name(
                component_info=component_info,
                component_name=component_name,
            )
            + ":latest"
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

    def run_scheduled_job(
        self,
        tool_name: str,
        component_name: str,
        component_info: ComponentInfo,
    ) -> str:
        if not isinstance(component_info.run, ScheduledRunInfo):
            raise ValueError(
                f"Invalid run info passed, it's not a ScheduledRunInfo: {component_info.run}"
            )
        # TODO: manage the tag in a nicer way overall
        image_name = (
            f"tool-{tool_name}/"
            + _get_component_image_name(
                component_info=component_info,
                component_name=component_name,
            )
            + ":latest"
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
        logger.debug(f"Sending job info {new_job}")
        # Using patch here does an upsert
        create_response = JobsJobResponse.model_validate(
            toolforge_client.patch(
                f"/jobs/v1/tool/{tool_name}/jobs/",
                json=new_job.model_dump(mode="json", exclude_none=True),
                verify=settings.verify_toolforge_api_cert,
            )
        )
        logger.debug(f"Deployed scheduled job {component_name}: {create_response}")
        # TODO: check if the job is actually running ok
        if create_response.job:
            return f"created scheduled job {create_response.job.name}"

        elif not create_response.messages:
            return f"unable to get job info, response from jobs api {create_response}"

        else:
            message = ""
            for level, messages in create_response.messages:
                if messages:
                    message += f"[{level}] ({', '.join(messages)})"
            return message

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

    def get_jobs(self, tool_name: str) -> list[JobsDefinedJob]:
        toolforge_client = get_toolforge_client()
        raw_response = toolforge_client.get(
            f"/jobs/v1/tool/{tool_name}/jobs",
            verify=get_settings().verify_toolforge_api_cert,
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
