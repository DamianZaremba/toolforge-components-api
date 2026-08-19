import subprocess
from typing import Any
from unittest.mock import MagicMock, _Call, create_autospec

import pytest
from toolforge_weld.api_client import ToolforgeClient

from components.client import get_toolforge_client
from components.exceptions import BuildFailed
from components.gen.toolforge_models import BuildsBuild, BuildsBuildParameters
from components.models.api_models import (
    DeploymentBuildInfo,
    DeploymentBuildState,
    SourceBuildInfo,
)
from components.runtime import toolforge
from components.runtime.toolforge import (
    _check_for_matching_build,
    _get_latest_component_build,
    _matches_parameters,
    _resolve_ref,
)
from tests.helpers import (
    get_dummy_builds_build,
    get_dummy_builds_build_parameters,
    get_dummy_continous_component_info,
    get_dummy_source_build_info,
    get_dummy_start_build_call,
    get_start_build_params,
)
from tests.utils import cases


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
                            build=get_dummy_source_build_info(
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
                            build=get_dummy_source_build_info(ref="custom-ref")
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
                            build=get_dummy_source_build_info(
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
                            build=get_dummy_source_build_info(use_latest_versions=True)
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
                            build=get_dummy_source_build_info(
                                use_deprecated_versions=True
                            )
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


class TestMatchesParameters:
    @cases(
        "build_info",
        [
            "use_latest_versions set",
            get_dummy_source_build_info(use_latest_versions=True),
        ],
        [
            "use_deprecated_versions set",
            get_dummy_source_build_info(use_deprecated_versions=True),
        ],
        ["ennvars set", get_dummy_source_build_info(envvars={"SOME": "envvar"})],
    )
    def test_fails_if_params_none_but_options_passed(self, build_info: SourceBuildInfo):
        existing_build_parameters = None

        assert not _matches_parameters(
            parameters=existing_build_parameters, build_info=build_info
        )

    @cases(
        "existing_build_parameters",
        [
            "use_latest_versions set",
            get_dummy_builds_build_parameters(use_latest_versions=True),
        ],
        [
            "use_deprecated_versions set",
            get_dummy_builds_build_parameters(use_deprecated_versions=True),
        ],
        ["ennvars set", get_dummy_builds_build_parameters(envvars={"SOME": "envvar"})],
    )
    def test_fails_if_params_passed_but_options_are_different(
        self, existing_build_parameters: BuildsBuildParameters
    ):
        build_info = get_dummy_source_build_info()

        assert not _matches_parameters(
            parameters=existing_build_parameters, build_info=build_info
        )


class TestResolveRef:
    def test_resolves_for_HEAD_if_ref_is_empty(self, monkeypatch: pytest.MonkeyPatch):
        build_info = get_dummy_source_build_info(ref="")
        expected_ref = "34306785891ddb972d9964baeefd9a7db9459aa8"
        expected_git_command = [
            "git",
            "ls-remote",
            build_info.repository.encoded_string(),
            "HEAD",
        ]
        git_ls_remote_stdout = f"{expected_ref}        HEAD"
        run_mock: MagicMock = create_autospec(subprocess.run)
        run_mock.return_value = subprocess.CompletedProcess(
            returncode=0, args=[], stdout=git_ls_remote_stdout
        )
        monkeypatch.setattr(target=toolforge.subprocess, name="run", value=run_mock)

        gotten_ref = _resolve_ref(build_info=build_info)

        assert gotten_ref == expected_ref
        run_mock.assert_called_once()
        assert run_mock.call_args[0][0] == expected_git_command

    def test_returns_empty_if_ls_remote_fails(self, monkeypatch: pytest.MonkeyPatch):
        build_info = get_dummy_source_build_info()
        run_mock = create_autospec(subprocess.run)
        run_mock.return_value = subprocess.CompletedProcess(returncode=1, args=[])
        monkeypatch.setattr(target=toolforge.subprocess, name="run", value=run_mock)

        gotten_ref = _resolve_ref(build_info=build_info)

        assert gotten_ref == ""
        run_mock.assert_called_once()

    def raises_BuildFailed_if_git_returns_no_output(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        build_info = get_dummy_source_build_info(ref="")
        git_ls_remote_stdout = ""
        run_mock: MagicMock = create_autospec(subprocess.run)
        run_mock.return_value = subprocess.CompletedProcess(
            returncode=0, args=[], stdout=git_ls_remote_stdout
        )
        monkeypatch.setattr(target=toolforge.subprocess, name="run", value=run_mock)

        with pytest.raises(BuildFailed):
            _resolve_ref(build_info=build_info)

        run_mock.assert_called_once()


class TestCheckForMatchingBuild:
    """This heavily depends on the subfunctions to be tested properly too."""

    def mock_builds_get(
        self, monkeypatch: pytest.MonkeyPatch, builds: list[dict[str, Any]]
    ):
        toolforge_client_mock = create_autospec(ToolforgeClient, instance=True)
        get_toolforge_client_mock = create_autospec(
            get_toolforge_client, return_value=toolforge_client_mock
        )
        toolforge_client_get_mock = toolforge_client_mock.get
        toolforge_client_get_mock.return_value = {"builds": builds}
        monkeypatch.setattr(
            target=toolforge,
            name="get_toolforge_client",
            value=get_toolforge_client_mock,
        )

        return toolforge_client_get_mock

    def test_returns_none_if_no_builds_returned_from_builds_api(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        toolforge_client_get_mock = self.mock_builds_get(
            monkeypatch=monkeypatch, builds=[]
        )

        gotten_match = _check_for_matching_build(
            component_name="does_not_matter",
            build_info=get_dummy_source_build_info(),
            tool_name="does_not_matter",
        )

        assert gotten_match is None
        toolforge_client_get_mock.assert_called_once()

    def test_returns_none_if_no_component_build_found(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        toolforge_client_get_mock = self.mock_builds_get(
            monkeypatch=monkeypatch,
            builds=[
                get_dummy_builds_build(
                    parameters=get_dummy_builds_build_parameters(
                        image_name="not-matching-component-name"
                    )
                ).model_dump()
            ],
        )

        gotten_match = _check_for_matching_build(
            component_name="my-component-name",
            build_info=get_dummy_source_build_info(),
            tool_name="not_relevant",
        )

        assert gotten_match is None
        toolforge_client_get_mock.assert_called_once()

    def test_returns_none_if_found_build_does_not_match_parameters(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        toolforge_client_get_mock = self.mock_builds_get(
            monkeypatch=monkeypatch,
            builds=[
                get_dummy_builds_build(
                    parameters=get_dummy_builds_build_parameters(
                        image_name="my-component-name"
                    )
                ).model_dump()
            ],
        )
        matches_parameters_mock: MagicMock = create_autospec(
            _matches_parameters, return_value=False
        )
        monkeypatch.setattr(
            target=toolforge, name="_matches_parameters", value=matches_parameters_mock
        )

        gotten_match = _check_for_matching_build(
            component_name="my-component-name",
            build_info=get_dummy_source_build_info(),
            tool_name="not_relevant",
        )

        assert gotten_match is None
        toolforge_client_get_mock.assert_called_once()
        matches_parameters_mock.assert_called_once()

    def test_returns_none_if_found_build_does_not_match_resolved_ref(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        toolforge_client_get_mock = self.mock_builds_get(
            monkeypatch=monkeypatch,
            builds=[
                get_dummy_builds_build(
                    resolved_ref="notmachingresolvedref",
                    parameters=get_dummy_builds_build_parameters(
                        image_name="my-component-name"
                    ),
                ).model_dump()
            ],
        )
        matches_parameters_mock: MagicMock = create_autospec(
            _matches_parameters, return_value=True
        )
        monkeypatch.setattr(
            target=toolforge, name="_matches_parameters", value=matches_parameters_mock
        )
        resolve_ref_mock: MagicMock = create_autospec(
            _resolve_ref, return_value="myresolvedref"
        )
        monkeypatch.setattr(
            target=toolforge, name="_resolve_ref", value=resolve_ref_mock
        )

        gotten_match = _check_for_matching_build(
            component_name="my-component-name",
            build_info=get_dummy_source_build_info(),
            tool_name="not_relevant",
        )

        assert gotten_match is None
        toolforge_client_get_mock.assert_called_once()
        matches_parameters_mock.assert_called_once()
        resolve_ref_mock.assert_called()

    def test_returns_matching_build_if_found_build_matches_params_and_ref(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        expected_build = get_dummy_builds_build(
            resolved_ref="myresolvedref",
            parameters=get_dummy_builds_build_parameters(
                image_name="my-component-name"
            ),
        )
        toolforge_client_get_mock = self.mock_builds_get(
            monkeypatch=monkeypatch,
            builds=[expected_build.model_dump()],
        )
        matches_parameters_mock: MagicMock = create_autospec(
            _matches_parameters, return_value=True
        )
        monkeypatch.setattr(
            target=toolforge, name="_matches_parameters", value=matches_parameters_mock
        )
        resolve_ref_mock: MagicMock = create_autospec(
            _resolve_ref, return_value="myresolvedref"
        )
        monkeypatch.setattr(
            target=toolforge, name="_resolve_ref", value=resolve_ref_mock
        )

        gotten_match = _check_for_matching_build(
            component_name="my-component-name",
            build_info=get_dummy_source_build_info(),
            tool_name="not_relevant",
        )

        assert gotten_match == expected_build
        toolforge_client_get_mock.assert_called_once()
        matches_parameters_mock.assert_called_once()
        resolve_ref_mock.assert_called()


class TestGetLatestComponentBuild:
    @cases(
        "builds",
        ["builds without images", [get_dummy_builds_build()]],
        [
            "builds with non-matching images",
            [
                get_dummy_builds_build(
                    parameters=get_dummy_builds_build_parameters(
                        image_name="not-my-component-name"
                    )
                )
            ],
        ],
    )
    def test_returns_none_if_no_builds_match_component_name(
        self, builds: list[BuildsBuild]
    ):
        expected_component_name = "my-component-name"

        gotten_latest_build = _get_latest_component_build(
            builds=builds,
            component_name=expected_component_name,
        )

        assert gotten_latest_build is None

    def test_returns_the_latest_build_if_many_match(self):
        expected_component_name = "my-component-name"
        expected_latest_build = get_dummy_builds_build(
            parameters=get_dummy_builds_build_parameters(
                image_name=expected_component_name
            ),
            start_time="2026-01-01T01:00:00",
        )
        builds = [
            get_dummy_builds_build(
                parameters=get_dummy_builds_build_parameters(
                    image_name="not-my-component-name"
                ),
                start_time="2026-02-01T00:00:00",
            ),
            get_dummy_builds_build(
                parameters=get_dummy_builds_build_parameters(
                    image_name="not-my-component-name"
                ),
                start_time="2026-02-01T00:00:00",
            ),
            expected_latest_build,
            get_dummy_builds_build(
                parameters=get_dummy_builds_build_parameters(
                    image_name=expected_component_name
                ),
                start_time="2026-01-01T00:00:00",
            ),
        ]

        gotten_latest_build = _get_latest_component_build(
            builds=builds,
            component_name=expected_component_name,
        )

        assert gotten_latest_build == expected_latest_build
