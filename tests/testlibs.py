from components.models.api_models import (
    ComponentInfo,
    Deployment,
    DeploymentBuildInfo,
    DeploymentBuildState,
    DeploymentState,
    RunInfo,
    SourceBuildInfo,
    ToolConfig,
)


def get_deployment_from_tool_config(
    *,
    tool_config: ToolConfig,
    with_build_state: DeploymentBuildState | None = None,
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
        config_version="1.0",
        components={
            "my-component": ComponentInfo(
                component_type="continuous",
                build=SourceBuildInfo(
                    repository="my-repo",
                    ref="main",
                ),
                run=RunInfo(
                    command="my-command",
                ),
            )
        },
    )
    params.update(overrides)
    return ToolConfig(**params)  # type: ignore
