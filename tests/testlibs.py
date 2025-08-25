from components.gen.toolforge_models import JobsDefinedJob
from components.models.api_models import (
    ContinuousComponentInfo,
    ContinuousRunInfo,
    Deployment,
    DeploymentBuildInfo,
    DeploymentBuildState,
    DeploymentRunInfo,
    DeploymentRunState,
    DeploymentState,
    SourceBuildInfo,
    ToolConfig,
)


def get_deployment_from_tool_config(
    *,
    tool_config: ToolConfig,
    with_build_state: DeploymentBuildState | None = None,
    with_run_state: DeploymentRunState | None = None,
    with_deployment_state: DeploymentState | None = None,
    **overrides,
) -> Deployment:
    params = dict(
        builds={
            component_name: DeploymentBuildInfo(
                build_id="my-build-id",
                build_status=(
                    with_build_state
                    if with_build_state is not None
                    else DeploymentBuildState.pending
                ),
            )
            for component_name in tool_config.components.keys()
        },
        runs={
            component_name: DeploymentRunInfo(
                run_status=(
                    with_run_state
                    if with_run_state is not None
                    else DeploymentRunState.pending
                )
            )
            for component_name in tool_config.components.keys()
        },
        tool_config=tool_config,
        deploy_id="my-deploy-id",
        creation_time="2021-06-01T00:00:00",
        status=(
            with_deployment_state
            if with_deployment_state is not None
            else DeploymentState.pending
        ),
        long_status="my long status",
    )
    params.update(overrides)
    return Deployment(**params)  # type: ignore


def get_tool_config(**overrides) -> ToolConfig:
    params = dict(
        config_version="v1beta1",
        components={
            "my-component": ContinuousComponentInfo(
                build=SourceBuildInfo(
                    repository="https://gitlab-example.wikimedia.org/my-repo.git",
                    ref="main",
                ),
                run=ContinuousRunInfo(
                    command="my-command",
                ),
            )
        },
    )
    params.update(overrides)
    return ToolConfig(**params)  # type: ignore


def get_defined_job(**overrides) -> JobsDefinedJob:
    params = dict(
        cmd="my cmd",
        continuous=True,
        cpu=None,
        emails=None,
        filelog=None,
        filelog_stderr=None,
        filelog_stdout=None,
        health_check=None,
        memory=None,
        image="my-image",
        imagename="my-imagename",
        image_state="",
        mount=None,
        name="my-job-name",
        port=None,
        replicas=None,
        retry=None,
        schedule=None,
        schedule_actual=None,
        status_long="",
        status_short="",
        timeout=None,
    )
    params.update(overrides)
    return JobsDefinedJob(**params)
