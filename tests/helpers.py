from typing import Any
from unittest.mock import _Call, call

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from components.gen.toolforge_models import BuildsBuild, BuildsBuildParameters
from components.models.api_models import (
    ComponentInfo,
    ContinuousComponentInfo,
    ContinuousRunInfo,
    DeployTokenResponse,
    SourceBuildInfo,
    ToolConfig,
    ToolConfigResponse,
    ToolDeploymentResponse,
)


def get_fake_tool_config(
    build: dict[str, Any] | None = None, **overrides
) -> ToolConfig:
    params = {
        "config_version": "v1beta1",
        "components": {
            "component1": {
                "build": {
                    "repository": "https://gitlab.wikimedia.org/toolforge-repos/sample-static-buildpack-app",
                    "ref": "main",
                },
                "component_type": "continuous",
                "run": {
                    "command": "some command",
                    "port": 8080,
                    "publish": "/",
                    "health_check_http": "/health",
                    "replicas": 2,
                    "memory": "256Mi",
                    "cpu": "0.5",
                    "filelog": False,
                    "mount": "none",
                },
            }
        },
    }
    params.update(overrides)
    if build is not None:
        params["components"]["component1"]["build"] = build
    return ToolConfig.model_validate(params)


def create_tool_config(
    client: TestClient, tool_name: str = "test-tool-1"
) -> ToolConfigResponse:
    tool_config = get_fake_tool_config()
    response = client.post(
        f"/v1/tool/{tool_name}/config",
        content=tool_config.model_dump_json(exclude_unset=True),
    )
    assert response.status_code == status.HTTP_200_OK
    return ToolConfigResponse.model_validate(response.json())


def delete_tool_config(
    client: TestClient, tool_name: str = "test-tool-1"
) -> ToolConfigResponse:
    response = client.delete(f"/v1/tool/{tool_name}/config")
    assert response.status_code == status.HTTP_200_OK
    return ToolConfigResponse.model_validate(response.json())


def create_deploy_token(
    client: TestClient, tool_name: str = "test-tool-1"
) -> DeployTokenResponse:
    delete_deploy_token(client, tool_name)

    response = client.post(f"/v1/tool/{tool_name}/deployment/token")
    assert response.status_code == status.HTTP_200_OK
    return DeployTokenResponse.model_validate(response.json())


def delete_deploy_token(
    client: TestClient, tool_name: str = "test-tool-1"
) -> DeployTokenResponse | None:
    response = client.delete(f"/v1/tool/{tool_name}/deployment/token")
    assert response.status_code in (status.HTTP_200_OK, status.HTTP_404_NOT_FOUND)
    if response.status_code == status.HTTP_200_OK:
        return DeployTokenResponse.model_validate(response.json())
    return None


def get_deploy_token(
    client: TestClient, tool_name: str = "test-tool-1"
) -> DeployTokenResponse:
    response = client.get(f"/v1/tool/{tool_name}/deployment/token")
    return DeployTokenResponse.model_validate(response.json())


def create_tool_deployment(
    client: TestClient, tool_name: str = "test-tool-1"
) -> ToolDeploymentResponse:
    response = client.post(f"/v1/tool/{tool_name}/deployment")
    assert response.status_code == status.HTTP_200_OK
    return ToolDeploymentResponse.model_validate(response.json())


def cases(params_str, *params_defs):
    """Simple wrapper around parametrize to add test titles in a more readable way.

    Use like:
    >>> @cases(
    >>>     "param1,param2",
    >>>     ["Test something", ["param1value1", "param2value1"]],
    >>>     ["Test something else", ["param1value2", "param2value2"]],
    >>> )
    >>> def test_mytest(param1, param2):
    >>>     ...

    So it shows in pytest like:
    ```
    tests/test_this_file.py::test_mytest[Test something] PASSED
    tests/test_this_file.py::test_mytest[Test something else] PASSED
    ```
    """
    test_names = [name for name, _ in params_defs]
    test_params = [params for _, params in params_defs]
    print(f"Parametrizing with: {params_str}\n{test_params}\nids={test_names}")

    def wrapper(func):
        return pytest.mark.parametrize(params_str, test_params, ids=test_names)(func)

    return wrapper


def get_dummy_source_build_info(**overrides) -> SourceBuildInfo:
    params = {
        "repository": "http://127.0.0.1/idontexist.git",
        "ref": "main",
    }
    return SourceBuildInfo.model_validate(params | overrides)


def get_dummy_continous_component_info(**overrides) -> ComponentInfo:
    params = {
        "build": get_dummy_source_build_info(),
        "run": ContinuousRunInfo(command="some-command"),
    }
    return ContinuousComponentInfo.model_validate(params | overrides)


def get_start_build_params(**overrides) -> dict[str, Any]:
    component_info: ComponentInfo = overrides.get(
        "component_info", get_dummy_continous_component_info()
    )

    params = {
        "build": component_info.build,
        "tool_name": "dummy-tool",
        "component_name": "dummy-component",
        "component_info": component_info,
        "force_build": False,
    }
    return params | overrides


def get_dummy_start_build_call(*args, **overrides) -> _Call:
    args = args or [
        "/builds/v1/tool/dummy-tool/builds",
    ]
    params = {
        "json": {
            "envvars": {},
            "image_name": "dummy-component",
            "ref": "main",
            "source_url": "http://127.0.0.1/idontexist.git",
            "use_deprecated_versions": False,
            "use_latest_versions": False,
        }
        | overrides,
        "verify": True,
    }
    return call(*args, **params)


def get_dummy_builds_build_parameters(**overrides) -> BuildsBuildParameters:
    defaults = {
        "source_url": "http://127.0.0.1/idontexist.git",
    }

    return BuildsBuildParameters.model_validate(defaults | overrides)


def get_dummy_builds_build(**overrides) -> BuildsBuild:
    defaults = {}

    return BuildsBuild.model_validate(defaults | overrides)
