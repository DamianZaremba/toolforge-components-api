import logging
from datetime import datetime

import requests
import yaml
from fastapi import BackgroundTasks, HTTPException, status
from pydantic import AnyHttpUrl

from ..deploy_task import do_deploy
from ..gen.toolforge_models import (
    BuildsBuild,
    JobsDefinedJob,
    JobsHttpHealthCheck,
    JobsScriptHealthCheck,
)
from ..models.api_models import (
    AnyGitUrl,
    ComponentInfo,
    ConfigVersion,
    ContinuousComponentInfo,
    ContinuousRunInfo,
    Deployment,
    DeploymentState,
    DeployToken,
    ScheduledComponentInfo,
    ScheduledRunInfo,
    SourceBuildInfo,
    ToolConfig,
)
from ..runtime.base import Runtime
from ..settings import get_settings
from ..storage import Storage
from ..storage.exceptions import NotFoundInStorage

logger = logging.getLogger(__name__)


def get_and_refetch_config_if_needed(toolname: str, storage: Storage) -> ToolConfig:
    logger.debug("Checking if I should update the config from source_url")
    config = get_tool_config(toolname=toolname, storage=storage)
    if config.source_url:
        logger.info(f"Re-fetching config from source_url: {config.source_url}")
        config = _fetch_config_from_url(url=config.source_url)
        config = update_tool_config(toolname=toolname, config=config, storage=storage)
        logger.info("Config re-updated from source_url")
        logger.debug(f"New config: {config}")
    else:
        logger.debug(f"No refetching of the config needed: {config}")

    return config


def get_tool_config(toolname: str, storage: Storage) -> ToolConfig:
    logger.info(f"Retrieving config for tool: {toolname}")
    try:
        config = storage.get_tool_config(toolname)
        logger.info(f"Config retrieved successfully for tool: {toolname}")
        return config
    except NotFoundInStorage as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving config for tool {toolname}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


def _fetch_config_from_url(url: AnyHttpUrl) -> ToolConfig:
    settings = get_settings()
    response = None
    try:
        response = requests.get(
            url.encoded_string(),
            headers={"User-Agent": settings.user_agent},
        )
        response.raise_for_status()
        config = ToolConfig.model_validate(yaml.safe_load(response.text))
    except Exception as error:
        logging.error(f"Got error trying to re-fetch the config from {url}: {error}")
        if response:
            logging.debug(f"response: {response.text}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to retrive config from source url {url}: {error}",
        ) from error

    return config


def update_tool_config(
    toolname: str, config: ToolConfig, storage: Storage
) -> ToolConfig:
    logger.info(f"Modifying config for tool: {toolname}")
    logger.debug(f"passed config: {config}")
    try:
        storage.set_tool_config(toolname, config)
        logger.info(f"Config updated successfully for tool: {toolname}")
        logger.debug(f"New config {config}")
        return config
    except Exception as e:
        logger.error(f"Error updating config for tool {toolname}: {str(e)}")
        logger.debug(f"Failed config {config}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


def delete_tool_config(toolname: str, storage: Storage) -> ToolConfig:
    logger.info(f"Deleting config for tool: {toolname}")
    try:
        old_config = storage.delete_tool_config(toolname)
        logger.info(f"Config deleted successfully for tool: {toolname}")
        return old_config
    except Exception as e:
        logger.error(f"Error deleting config for tool {toolname}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


def _get_build_for_job(
    job: JobsDefinedJob, existing_builds: list[BuildsBuild]
) -> SourceBuildInfo | None:
    for build in existing_builds:
        if not build.destination_image:
            return None
        # ugly matching, but good enough
        if build.destination_image.endswith(job.image):
            if not build.parameters or not build.parameters.source_url:
                return None

            return SourceBuildInfo(
                repository=AnyGitUrl(build.parameters.source_url),
                # for now we require a ref, remove once ref can be optional
                ref=build.parameters.ref or "HEAD",
            )

    return None


def _get_run_for_job(job: JobsDefinedJob) -> ScheduledRunInfo | ContinuousRunInfo:
    # we need to strip launcher because jobs adds it automatically but then does not remove it when getting the job
    command = job.cmd.split("launcher ", 1)[-1]
    params = {"command": command}

    if job.health_check:
        match job.health_check:
            case JobsHttpHealthCheck():
                params["health_check_http"] = job.health_check.path
            case JobsScriptHealthCheck():
                params["health_check_script"] = job.health_check.script

    for param_name in [
        "cpu",
        "emails",
        "filelog",
        "filelog_stderr",
        "filelog_stdout",
        "memory",
        "mount",
        "port",
        "replicas",
        "schedule",
        "retry",
        "timeout",
    ]:
        value = getattr(job, param_name, None)
        if value is not None:
            params[param_name] = value

    if job.continuous:
        return ContinuousRunInfo.model_validate(params)

    return ScheduledRunInfo.model_validate(params)


def _get_component_for_job(
    job: JobsDefinedJob, existing_builds: list[BuildsBuild]
) -> tuple[ComponentInfo | None, str]:
    build = _get_build_for_job(job=job, existing_builds=existing_builds)
    if not build:
        return (
            None,
            f"Job {job.name} seems not to be a build-service based job (or no build found for it), skipping",
        )

    run = _get_run_for_job(job=job)
    match run:
        case ScheduledRunInfo():
            return ScheduledComponentInfo(build=build, run=run), ""
        case ContinuousRunInfo():
            return ContinuousComponentInfo(build=build, run=run), ""
        case _:
            logger.debug(f"unknown run type {run}")
            return (
                None,
                f"Job {job.name} is not a continuous or scheduled job, it's not supported yet, skipping",
            )


def generate_tool_config(
    toolname: str, runtime: Runtime
) -> tuple[ToolConfig | None, list[str]]:
    messages: list[str] = []
    logger.info(f"Generating config for tool: {toolname}")
    jobs = runtime.get_jobs(tool_name=toolname)
    logger.debug(f"Got jobs: {jobs}")
    builds = runtime.get_builds(tool_name=toolname)
    logger.debug(f"Got builds: {builds}")
    components: dict[str, ComponentInfo] = {}
    for job in jobs:
        maybe_component, new_message = _get_component_for_job(
            job=job, existing_builds=builds
        )
        if new_message:
            messages.append(new_message)
        if maybe_component:
            components[job.name] = maybe_component

    if not components:
        logger.debug("No components could be generated, using example.")
        return None, messages

    logger.debug(f"Got components: {components}")
    return (
        ToolConfig(components=components, config_version=ConfigVersion.V1_BETA1),
        messages,
    )


def get_tool_deployment(
    tool_name: str, deployment_name: str, storage: Storage
) -> Deployment:
    logger.info(f"Retrieving deployment {deployment_name} for tool {tool_name}")
    try:
        config = storage.get_deployment(
            tool_name=tool_name, deployment_name=deployment_name
        )
        logger.info(f"Deployment retrieved successfully for tool: {tool_name}")
        return config

    except NotFoundInStorage as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    except Exception as e:
        logger.error(f"Error retrieving deployment for tool {tool_name}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


def cancel_tool_deployment(
    tool_name: str, deployment_name: str, storage: Storage
) -> Deployment:
    logger.info(f"Cancelling deployment {deployment_name} for tool {tool_name}")
    try:
        deployment = storage.get_deployment(
            tool_name=tool_name, deployment_name=deployment_name
        )
        if deployment.status not in (DeploymentState.pending, DeploymentState.running):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Deployment can't be cancelled, it's state is {deployment.status.value}",
            )

        deployment.status = DeploymentState.cancelling
        storage.update_deployment(tool_name=tool_name, deployment=deployment)
        logger.info(
            f"Deployment {deployment_name} flagged for cancelling successfully for tool {tool_name}"
        )
        return deployment

    except NotFoundInStorage as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    except HTTPException:
        # bubble up http exceptions for the api to return
        raise

    except Exception as e:
        logger.error(f"Error cancelling deployment for tool {tool_name}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


def get_latest_deployment(tool_name: str, storage: Storage) -> Deployment:
    deployments = list_tool_deployments(tool_name=tool_name, storage=storage)
    sorted_deployments = sorted(
        deployments, key=lambda d: datetime.strptime(d.creation_time, "%Y%m%d-%H%M%S")
    )
    return sorted_deployments[-1]


def list_tool_deployments(tool_name: str, storage: Storage) -> list[Deployment]:
    logger.info(f"Listing deployments for tool: {tool_name}")
    try:
        deployments = storage.list_deployments(tool_name)
        if not deployments:
            raise NotFoundInStorage(f"No deployments found for tool: {tool_name}")
        return deployments
    except NotFoundInStorage as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error listing deployments for tool {tool_name}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


def _check_active_deployments_limit(storage: Storage, tool_name: str) -> None:
    settings = get_settings()
    logger.debug(f"Checking active deployments limit for {tool_name}.")
    try:
        all_deployments = storage.list_deployments(tool_name=tool_name)
        active_deployments = [
            deployment
            for deployment in all_deployments
            if deployment.status in (DeploymentState.running, DeploymentState.pending)
        ]
        if len(active_deployments) >= settings.max_active_deployments:
            logger.debug(
                f"Tool {tool_name} has reach it's active deployment limit {settings.max_active_deployments}, "
                "preventing a new deployment"
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"There's already {len(active_deployments)}, the limit is "
                    f"{settings.max_active_deployments}. Wait for some deployments to finish. You can also cancel some deployments"
                ),
            )
    except NotFoundInStorage:
        pass

    logger.debug(
        f"Tool {tool_name} has not reached the limit of active deployments yet, continuing..."
    )


def create_tool_deployment(
    tool_name: str,
    deployment: Deployment,
    storage: Storage,
    runtime: Runtime,
    background_tasks: BackgroundTasks,
) -> Deployment:
    _check_active_deployments_limit(storage=storage, tool_name=tool_name)
    tool_config = get_tool_config(toolname=tool_name, storage=storage)

    logger.info(f"Creating deployment for tool: {tool_name}")
    try:
        storage.create_deployment(tool_name=tool_name, deployment=deployment)
        logger.info(f"Created deployment {deployment} for tool {tool_name}")
    except Exception as e:
        logger.error(
            f"Error creating deployment {deployment} for tool {tool_name}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )

    background_tasks.add_task(
        do_deploy,
        deployment=deployment,
        tool_config=tool_config,
        tool_name=tool_name,
        storage=storage,
        runtime=runtime,
    )

    return deployment


def delete_tool_deployment(
    tool_name: str, deployment_name: str, storage: Storage
) -> Deployment:
    logger.info(f"Deleting deployment {deployment_name} for tool {tool_name}")
    try:
        deployment = storage.delete_deployment(tool_name, deployment_name)
        logger.info(f"Deployment deleted successfully for tool: {tool_name}")
        return deployment
    except NotFoundInStorage as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(
            f"Error deleting deployment {deployment_name} for tool {tool_name}: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


def _create_new_token(toolname: str, storage: Storage) -> DeployToken:
    new_token = DeployToken()
    storage.set_deploy_token(toolname, new_token)
    logger.info(f"Deploy token created for tool: {toolname}")
    return new_token


def _raise_if_deploy_token_exists(toolname: str, storage: Storage) -> None:
    try:
        storage.get_deploy_token(toolname)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Deploy token already exists. Use the 'refresh' subcommand or PUT /tool/{toolname}/deployment/token "
                "to refresh it."
            ),
        )
    except NotFoundInStorage:
        pass


def create_deploy_token(toolname: str, storage: Storage) -> DeployToken:
    logger.info(f"Creating deploy token for tool: {toolname}")
    try:
        _raise_if_deploy_token_exists(toolname, storage)
        return _create_new_token(toolname, storage)
    except HTTPException:
        raise
    # TODO: use a global exception handler for generic exceptions instead
    except Exception as e:
        logger.error(f"Error creating deploy token for tool {toolname}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


def update_deploy_token(toolname: str, storage: Storage) -> DeployToken:
    logger.info(f"Checking if deploy token exists for tool: {toolname}")
    try:
        storage.get_deploy_token(toolname)
        return _create_new_token(toolname, storage)
    except NotFoundInStorage as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


def get_deploy_token(toolname: str, storage: Storage) -> DeployToken:
    logger.info(f"Retrieving deploy token for tool: {toolname}")
    try:
        token = storage.get_deploy_token(toolname)
        logger.info(f"Deploy token retrieved for tool: {toolname}")
        return token
    except NotFoundInStorage as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving deploy token for tool {toolname}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


def delete_deploy_token(toolname: str, storage: Storage) -> DeployToken:
    logger.info(f"Deleting deploy token for tool: {toolname}")
    try:
        token = storage.delete_deploy_token(toolname)
        logger.info(f"Deploy token deleted for tool: {toolname}")
        return token
    except NotFoundInStorage as e:
        logger.warning(str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting deploy token for tool {toolname}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
