import datetime
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time
from pytest import MonkeyPatch
from toolforge_weld.api_client import ToolforgeClient

from components.deploy_task import do_deploy
from components.gen.toolforge_models import BuildsBuildStatus
from components.models.api_models import (
    ComponentInfo,
    Deployment,
    DeploymentBuildInfo,
    DeploymentBuildState,
    DeploymentRunInfo,
    DeploymentRunState,
    DeploymentState,
    RunInfo,
    SourceBuildInfo,
)
from components.storage.mock import MockStorage

from .testlibs import get_deployment_from_tool_config, get_tool_config


class TestDoDeploy:
    def test_starts_build_and_runs_single_continuous_component(
        self, monkeypatch: MonkeyPatch
    ):
        my_storage = MockStorage()
        my_tool_config = get_tool_config()
        my_deployment = get_deployment_from_tool_config(tool_config=my_tool_config)
        my_deployment = get_deployment_from_tool_config(tool_config=my_tool_config)
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.deploy_task.get_toolforge_client",
            lambda: toolforge_client_mock,
        )
        toolforge_client_mock.post.return_value = {"new_build": {"name": "my-build"}}
        toolforge_client_mock.get.return_value = {
            "build": {"status": BuildsBuildStatus.BUILD_SUCCESS.value}
        }

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.successful,
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.successful,
                    )
                },
                status=DeploymentState.successful,
                long_status="I will not be checked",
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
        )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        expected_deployments[0].long_status = gotten_deployments[0].long_status
        assert gotten_deployments == expected_deployments
        toolforge_client_mock.patch.assert_called_once()

    @pytest.mark.parametrize(
        "build_status",
        [
            BuildsBuildStatus.BUILD_FAILURE,
            BuildsBuildStatus.BUILD_CANCELLED,
        ],
    )
    def test_fails_deployment_if_build_fails(
        self, monkeypatch: MonkeyPatch, build_status: BuildsBuildStatus
    ):
        my_storage = MockStorage()
        my_tool_config = get_tool_config()
        my_deployment = get_deployment_from_tool_config(
            tool_config=my_tool_config, with_build_state=DeploymentBuildState.failed
        )
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.deploy_task.get_toolforge_client",
            lambda: toolforge_client_mock,
        )
        toolforge_client_mock.post.return_value = {"new_build": {"name": "my-build"}}
        toolforge_client_mock.get.return_value = {
            "build": {"status": build_status.value}
        }

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.failed,
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.pending,
                    )
                },
                status=DeploymentState.failed,
                long_status="I will not be checked",
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
        )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        expected_deployments[0].long_status = gotten_deployments[0].long_status
        assert gotten_deployments == expected_deployments
        toolforge_client_mock.patch.assert_not_called()

    @pytest.mark.parametrize(
        "build_status",
        [
            BuildsBuildStatus.BUILD_RUNNING,
            BuildsBuildStatus.BUILD_UNKNOWN,
        ],
    )
    def test_fails_deployment_if_build_times_out(
        self,
        monkeypatch: MonkeyPatch,
        build_status: BuildsBuildStatus,
    ):
        my_storage = MockStorage()
        my_tool_config = get_tool_config()
        my_deployment = get_deployment_from_tool_config(tool_config=my_tool_config)
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.deploy_task.get_toolforge_client",
            lambda: toolforge_client_mock,
        )
        toolforge_client_mock.post.return_value = {"new_build": {"name": "my-build"}}
        toolforge_client_mock.get.return_value = {
            "build": {"status": build_status.value}
        }

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.pending,
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.pending,
                    )
                },
                status=DeploymentState.failed,
                long_status="I will not be checked",
            )
        ]

        with freeze_time(
            datetime.datetime.now(),
            auto_tick_seconds=60 * 60 * 24,
            tick=True,
        ):
            do_deploy(
                deployment=my_deployment,
                storage=my_storage,
                tool_config=my_tool_config,
                tool_name="my-tool",
            )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        expected_deployments[0].long_status = gotten_deployments[0].long_status
        assert gotten_deployments == expected_deployments
        toolforge_client_mock.patch.assert_not_called()

    def test_times_out_deployment_not_finished_in_1h(
        self,
        monkeypatch: MonkeyPatch,
    ):
        my_storage = MockStorage()
        my_tool_config = get_tool_config()
        my_deployment = get_deployment_from_tool_config(tool_config=my_tool_config)
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.deploy_task.get_toolforge_client",
            lambda: toolforge_client_mock,
        )
        toolforge_client_mock.post.return_value = {"new_build": {"name": "my-build"}}
        toolforge_client_mock.get.return_value = {
            "build": {"status": BuildsBuildStatus.BUILD_SUCCESS.value}
        }

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.pending,
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.pending,
                    )
                },
                status=DeploymentState.failed,
                long_status="I will not be checked",
            )
        ]

        with freeze_time(
            datetime.datetime.now(),
            auto_tick_seconds=60 * 60 * 24,
            tick=True,
        ):
            do_deploy(
                deployment=my_deployment,
                storage=my_storage,
                tool_config=my_tool_config,
                tool_name="my-tool",
            )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        expected_deployments[0].long_status = gotten_deployments[0].long_status
        assert gotten_deployments == expected_deployments
        toolforge_client_mock.patch.assert_not_called()

    def test_fails_deployment_if_run_fails(self, monkeypatch: MonkeyPatch):
        my_storage = MockStorage()
        my_tool_config = get_tool_config()
        my_deployment = get_deployment_from_tool_config(tool_config=my_tool_config)
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.deploy_task.get_toolforge_client",
            lambda: toolforge_client_mock,
        )
        toolforge_client_mock.post.return_value = {"new_build": {"name": "my-build"}}
        toolforge_client_mock.get.return_value = {
            "build": {"status": BuildsBuildStatus.BUILD_SUCCESS}
        }
        toolforge_client_mock.patch.side_effect = Exception("Ayayayay!")

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.successful,
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.failed,
                    )
                },
                status=DeploymentState.failed,
                long_status="I will not be checked",
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
        )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        expected_deployments[0].long_status = gotten_deployments[0].long_status
        assert gotten_deployments == expected_deployments
        toolforge_client_mock.patch.assert_called_with(
            "/jobs/v1/tool/my-tool/jobs/",
            json={
                "cmd": "my-command",
                "continuous": True,
                "name": "my-component",
                "imagename": "tool-my-tool/my-component:latest",
            },
            verify=True,
        )

    def test_fails_deployment_if_one_run_fails_but_others_succeed(
        self, monkeypatch: MonkeyPatch
    ):
        my_storage = MockStorage()
        my_tool_config = get_tool_config(
            components={
                "failed-component": ComponentInfo(
                    component_type="continuous",
                    build=SourceBuildInfo(
                        repository="my-repo",
                        ref="main",
                    ),
                    run=RunInfo(
                        command="my-command",
                    ),
                ),
                "successful-component": ComponentInfo(
                    component_type="continuous",
                    build=SourceBuildInfo(
                        repository="my-repo",
                        ref="main",
                    ),
                    run=RunInfo(
                        command="my-command",
                    ),
                ),
            }
        )
        my_deployment = get_deployment_from_tool_config(tool_config=my_tool_config)
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.deploy_task.get_toolforge_client",
            lambda: toolforge_client_mock,
        )
        toolforge_client_mock.post.return_value = {"new_build": {"name": "my-build"}}
        toolforge_client_mock.get.return_value = {
            "build": {"status": BuildsBuildStatus.BUILD_SUCCESS}
        }
        toolforge_client_mock.patch.side_effect = [
            Exception("Ayayayay!"),
            {},
        ]

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "failed-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.successful,
                    ),
                    "successful-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.successful,
                    ),
                },
                runs={
                    "failed-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.failed,
                    ),
                    "successful-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.pending,
                    ),
                },
                status=DeploymentState.failed,
                long_status="I will not be checked",
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
        )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        expected_deployments[0].long_status = gotten_deployments[0].long_status
        assert gotten_deployments == expected_deployments
        # runs are serial for now, it will fail on the first and not try the second
        toolforge_client_mock.patch.assert_called_once_with(
            "/jobs/v1/tool/my-tool/jobs/",
            json={
                "cmd": "my-command",
                "continuous": True,
                "name": "failed-component",
                "imagename": "tool-my-tool/failed-component:latest",
            },
            verify=True,
        )
