from typing import Any
from unittest.mock import _Call, call, create_autospec

import pytest
from toolforge_weld.api_client import ToolforgeClient

from components.client import get_toolforge_client
from components.models.api_models import (
    ComponentInfo,
    ContinuousComponentInfo,
    ContinuousRunInfo,
    DeploymentBuildInfo,
    DeploymentBuildState,
    SourceBuildInfo,
)
from components.runtime import toolforge
from tests.utils import cases


def get_dummy_source_build(**overrides) -> SourceBuildInfo:
    params = {
        "repository": "http://127.0.0.1/idontexist.git",
        "ref": "main",
        "use_latest_versions": False,
        "use_deprecated_versions": False,
    }
    return SourceBuildInfo.model_validate(params | overrides)


def get_dummy_continous_component_info(**overrides) -> ComponentInfo:
    params = {
        "build": get_dummy_source_build(),
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


class TestToolforgeRuntime:
    class TestStartBuild:
        @cases(
            "build_params,expected_call",
            [
                "Passes the defaults correctly",
                (
                    get_start_build_params(
                        component_info=get_dummy_continous_component_info()
                    ),
                    get_dummy_start_build_call(),
                ),
            ],
            [
                "Passes the envvars option",
                (
                    get_start_build_params(
                        component_info=get_dummy_continous_component_info(
                            build=get_dummy_source_build(
                                envvars={"VAR1": "var1value", "VAR2": "var2value"}
                            )
                        )
                    ),
                    get_dummy_start_build_call(
                        envvars={"VAR1": "var1value", "VAR2": "var2value"},
                    ),
                ),
            ],
            [
                "Passes the ref option",
                (
                    get_start_build_params(
                        component_info=get_dummy_continous_component_info(
                            build=get_dummy_source_build(ref="custom-ref")
                        )
                    ),
                    get_dummy_start_build_call(ref="custom-ref"),
                ),
            ],
            [
                "Passes the source_url option",
                (
                    get_start_build_params(
                        component_info=get_dummy_continous_component_info(
                            build=get_dummy_source_build(
                                repository="http://127.0.0.1/custom-repository.git"
                            )
                        )
                    ),
                    get_dummy_start_build_call(
                        source_url="http://127.0.0.1/custom-repository.git"
                    ),
                ),
            ],
            [
                "Passes the component_name as image_name",
                (
                    get_start_build_params(
                        component_name="custom-component-name",
                        component_info=get_dummy_continous_component_info(),
                    ),
                    get_dummy_start_build_call(
                        image_name="custom-component-name",
                    ),
                ),
            ],
            [
                "Passes the use_latest_versions option",
                (
                    get_start_build_params(
                        component_info=get_dummy_continous_component_info(
                            build=get_dummy_source_build(use_latest_versions=True)
                        ),
                    ),
                    get_dummy_start_build_call(use_latest_versions=True),
                ),
            ],
            [
                "Passes the use_deprecated_versions option",
                (
                    get_start_build_params(
                        component_info=get_dummy_continous_component_info(
                            build=get_dummy_source_build(use_deprecated_versions=True)
                        ),
                    ),
                    get_dummy_start_build_call(use_deprecated_versions=True),
                ),
            ],
        )
        def test_passes_the_parameters_to_builds_api(
            self,
            build_params: dict[str, Any],
            expected_call: _Call,
            monkeypatch: pytest.MonkeyPatch,
        ):
            expected_response = DeploymentBuildInfo(
                build_id="no-id-yet",
                build_status=DeploymentBuildState.pending,
                build_image="no-image-yet",
                build_long_status="Not started yet",
            )
            toolforge_client_mock = create_autospec(ToolforgeClient, instance=True)
            toolforge_client_mock.post.return_value = {
                "new_build": {"name": "no-id-yet"}
            }
            get_toolforge_client_mock = create_autospec(
                get_toolforge_client, return_value=toolforge_client_mock
            )
            monkeypatch.setattr(
                name="get_toolforge_client",
                target=toolforge,
                value=get_toolforge_client_mock,
            )
            matching_build_mock = create_autospec(
                toolforge._check_for_matching_build, return_value=False
            )
            monkeypatch.setattr(
                name="_check_for_matching_build",
                target=toolforge,
                value=matching_build_mock,
            )
            my_runtime = toolforge.ToolforgeRuntime()

            gotten_response = my_runtime.start_build(**build_params)

            assert toolforge_client_mock.post.call_args == expected_call
            assert gotten_response == expected_response

            get_toolforge_client_mock.assert_called()
