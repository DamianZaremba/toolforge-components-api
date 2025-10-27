import datetime
from unittest.mock import MagicMock, call

import pytest
import requests
from fastapi import status
from freezegun import freeze_time
from pytest import MonkeyPatch
from requests import ReadTimeout
from toolforge_weld.api_client import ToolforgeClient

from components.deploy_task import _retry_http_failures, do_deploy
from components.gen.toolforge_models import (
    BuildsBuildStatus,
    JobsJobListResponse,
    JobsJobResponse,
    JobsResponseMessages,
)
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
    SourceBuildReference,
    ToolConfig,
)
from components.runtime.utils import get_runtime
from components.settings import get_settings
from components.storage.mock import MockStorage

from .testlibs import get_defined_job, get_deployment_from_tool_config, get_tool_config


class TestDoDeploy:
    def test_skip_build_if_no_change_in_ref_hash_and_existing_build(
        self,
        monkeypatch: MonkeyPatch,
    ):
        my_storage = MockStorage()
        my_tool_config = get_tool_config()
        my_deployment = get_deployment_from_tool_config(tool_config=my_tool_config)
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.runtime.toolforge.get_toolforge_client",
            lambda: toolforge_client_mock,
        )

        monkeypatch.setattr(
            "components.runtime.toolforge._resolve_ref",
            lambda *args, **kwargs: "same-ref-as-build",
        )

        existing_build_id = "random_existing_build_id"
        toolforge_client_mock.get.side_effect = [
            {
                "builds": [
                    {
                        "build_id": existing_build_id,
                        "name": "my-component",
                        "resolved_ref": "same-ref-as-build",
                        "destination_image": "my-tool/my-component:latest",
                        "status": BuildsBuildStatus.BUILD_SUCCESS.value,
                        "parameters": {
                            "image_name": "my-component",
                            "source_url": "my-url",
                        },
                    }
                ]
            },
            {"build": {"status": BuildsBuildStatus.BUILD_SUCCESS}},
        ]
        toolforge_client_mock.post.return_value = {
            "new_build": {"name": "my-component"}
        }
        toolforge_client_mock.patch.return_value = JobsJobResponse(
            messages=JobsResponseMessages(
                error=None, info=["created continuous job my-job-name"], warning=None
            ),
        ).model_dump()

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id=existing_build_id,
                        build_status=DeploymentBuildState.skipped,
                        build_long_status="Reusing existing build",
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.successful,
                        run_long_status="[info] (created continuous job my-job-name)",
                    )
                },
                tool_config=get_tool_config(),
                status=DeploymentState.successful,
                long_status="I will not be checked",
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
            runtime=get_runtime(settings=get_settings()),
        )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        expected_deployments[0].long_status = gotten_deployments[0].long_status
        assert gotten_deployments == expected_deployments
        toolforge_client_mock.patch.assert_called_once()

    @pytest.mark.parametrize(
        "existing_build_start_status",
        [
            BuildsBuildStatus.BUILD_PENDING,
            BuildsBuildStatus.BUILD_RUNNING,
        ],
    )
    def test_follow_up_existing_build_if_no_change_in_ref_hash_and_existing_build_running(
        self,
        monkeypatch: MonkeyPatch,
        existing_build_start_status: BuildsBuildStatus,
    ):
        my_storage = MockStorage()
        my_tool_config = get_tool_config()
        my_deployment = get_deployment_from_tool_config(tool_config=my_tool_config)
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.runtime.toolforge.get_toolforge_client",
            lambda: toolforge_client_mock,
        )

        monkeypatch.setattr(
            "components.runtime.toolforge._resolve_ref",
            lambda *args, **kwargs: "same-ref-as-build",
        )

        existing_build_id = "random_existing_build_id"
        toolforge_client_mock.get.side_effect = [
            {
                "builds": [
                    {
                        "build_id": existing_build_id,
                        "name": "my-component",
                        "resolved_ref": "same-ref-as-build",
                        "destination_image": "my-tool/my-component:latest",
                        "status": existing_build_start_status.value,
                        "parameters": {
                            "image_name": "my-component",
                            "source_url": "my-url",
                        },
                    }
                ]
            },
            {"build": {"status": BuildsBuildStatus.BUILD_SUCCESS}},
            JobsJobListResponse(jobs=[]).model_dump(),
        ]
        toolforge_client_mock.post.return_value = {
            "new_build": {"name": "my-component"}
        }
        toolforge_client_mock.patch.return_value = JobsJobResponse(
            messages=JobsResponseMessages(
                error=None, info=["created continuous job my-job-name"], warning=None
            ),
        ).model_dump()
        toolforge_client_mock.delete.return_value = JobsResponseMessages().model_dump()

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id=existing_build_id,
                        build_status=DeploymentBuildState.successful,
                        build_long_status="You can see the logs with `toolforge build logs random_existing_build_id`",
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.successful,
                        run_long_status="[info] (created continuous job my-job-name)",
                    )
                },
                tool_config=get_tool_config(),
                status=DeploymentState.successful,
                long_status="I will not be checked",
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
            runtime=get_runtime(settings=get_settings()),
        )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        expected_deployments[0].long_status = gotten_deployments[0].long_status
        assert gotten_deployments == expected_deployments
        toolforge_client_mock.patch.assert_called_once()

    def test_does_not_skip_build_if_no_change_in_ref_hash_and_existing_build_but_force_build_passed(
        self,
        monkeypatch: MonkeyPatch,
    ):
        my_storage = MockStorage()
        my_tool_config = get_tool_config()
        my_deployment = get_deployment_from_tool_config(
            tool_config=my_tool_config, force_build=True
        )
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.runtime.toolforge.get_toolforge_client",
            lambda: toolforge_client_mock,
        )

        monkeypatch.setattr(
            "components.runtime.toolforge._resolve_ref",
            lambda *args, **kwargs: "same-ref-as-build",
        )

        toolforge_client_mock.post.return_value = {
            "new_build": {"name": "new_build_name"}
        }
        toolforge_client_mock.get.return_value = {
            "build": {"status": BuildsBuildStatus.BUILD_SUCCESS}
        }
        toolforge_client_mock.patch.return_value = JobsJobResponse(
            messages=JobsResponseMessages(
                error=None, info=["created continuous job my-job-name"], warning=None
            ),
        ).model_dump()

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="new_build_name",
                        build_status=DeploymentBuildState.successful,
                        build_long_status="You can see the logs with `toolforge build logs new_build_name`",
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.successful,
                        run_long_status="[info] (created continuous job my-job-name)",
                    )
                },
                tool_config=get_tool_config(),
                status=DeploymentState.successful,
                long_status="I will not be checked",
                force_build=True,
            ),
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
            runtime=get_runtime(settings=get_settings()),
        )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        expected_deployments[0].long_status = gotten_deployments[0].long_status
        assert gotten_deployments == expected_deployments
        toolforge_client_mock.patch.assert_called_once()
        toolforge_client_mock.post.assert_called_once()

    def test_starts_build_and_runs_single_continuous_component(
        self, monkeypatch: MonkeyPatch
    ):
        my_storage = MockStorage()
        my_tool_config = get_tool_config()
        my_deployment = get_deployment_from_tool_config(tool_config=my_tool_config)
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.runtime.toolforge.get_toolforge_client",
            lambda: toolforge_client_mock,
        )
        toolforge_client_mock.post.return_value = {"new_build": {"name": "my-build"}}
        toolforge_client_mock.get.return_value = {
            "build": {"status": BuildsBuildStatus.BUILD_SUCCESS.value}
        }
        toolforge_client_mock.patch.return_value = JobsJobResponse(
            messages=JobsResponseMessages(
                error=None, info=["created continuous job my-job-name"], warning=None
            ),
        ).model_dump()

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.successful,
                        build_long_status="You can see the logs with `toolforge build logs my-build`",
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.successful,
                        run_long_status="[info] (created continuous job my-job-name)",
                    )
                },
                tool_config=get_tool_config(),
                status=DeploymentState.successful,
                long_status="I will not be checked",
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
            runtime=get_runtime(settings=get_settings()),
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
            "components.runtime.toolforge.get_toolforge_client",
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
                        build_long_status="You can see the logs with `toolforge build logs my-build`",
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.skipped,
                        run_long_status="Skipped due to previous failure",
                    )
                },
                tool_config=get_tool_config(),
                status=DeploymentState.failed,
                long_status="I will not be checked",
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
            runtime=get_runtime(settings=get_settings()),
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
            "components.runtime.toolforge.get_toolforge_client",
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
                        build_long_status="Not started yet",
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.skipped,
                        run_long_status="Skipped due to previous failure",
                    )
                },
                tool_config=get_tool_config(),
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
                runtime=get_runtime(settings=get_settings()),
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
            "components.runtime.toolforge.get_toolforge_client",
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
                        build_long_status="Not started yet",
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.skipped,
                        run_long_status="Skipped due to previous failure",
                    )
                },
                tool_config=get_tool_config(),
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
                runtime=get_runtime(settings=get_settings()),
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
            "components.runtime.toolforge.get_toolforge_client",
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
                        build_long_status="You can see the logs with `toolforge build logs my-build`",
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.failed,
                        run_long_status="Ayayayay!",
                    )
                },
                tool_config=get_tool_config(),
                status=DeploymentState.failed,
                long_status="I will not be checked",
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
            runtime=get_runtime(settings=get_settings()),
        )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        expected_deployments[0].long_status = gotten_deployments[0].long_status
        assert gotten_deployments == expected_deployments
        toolforge_client_mock.patch.assert_called_with(
            "/jobs/v1/tool/my-tool/jobs/",
            json={
                "job_type": "continuous",
                "cmd": "my-command",
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
                "failed-component": ContinuousComponentInfo(
                    build=SourceBuildInfo(
                        repository="https://gitlab-example.wikimedia.org/my-repo.git",
                        ref="main",
                    ),
                    run=ContinuousRunInfo(
                        command="my-command",
                    ),
                ),
                "successful-component": ContinuousComponentInfo(
                    component_type="continuous",
                    build=SourceBuildInfo(
                        repository="https://gitlab-example.wikimedia.org/my-repo.git",
                        ref="main",
                    ),
                    run=ContinuousRunInfo(
                        command="my-command",
                    ),
                ),
            }
        )
        my_deployment = get_deployment_from_tool_config(tool_config=my_tool_config)
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.runtime.toolforge.get_toolforge_client",
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
                        build_long_status="You can see the logs with `toolforge build logs my-build`",
                    ),
                    "successful-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.successful,
                        build_long_status="You can see the logs with `toolforge build logs my-build`",
                    ),
                },
                runs={
                    "failed-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.failed,
                        run_long_status="Ayayayay!",
                    ),
                    "successful-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.skipped,
                        run_long_status="Skipped due to previous failure",
                    ),
                },
                tool_config=my_tool_config,
                status=DeploymentState.failed,
                long_status="I will not be checked",
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
            runtime=get_runtime(settings=get_settings()),
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
                "job_type": "continuous",
                "cmd": "my-command",
                "name": "failed-component",
                "imagename": "tool-my-tool/failed-component:latest",
            },
            verify=True,
        )

    def test_cancels_builds_when_deploy_is_cancelled(self, monkeypatch: MonkeyPatch):
        my_storage = MockStorage()
        my_tool_config = get_tool_config()
        my_deployment = get_deployment_from_tool_config(
            tool_config=my_tool_config, with_build_state=DeploymentBuildState.failed
        )
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.runtime.toolforge.get_toolforge_client",
            lambda: toolforge_client_mock,
        )
        toolforge_client_mock.post.return_value = {"new_build": {"name": "my-build"}}
        toolforge_client_mock.get.return_value = {
            "build": {"status": BuildsBuildStatus.BUILD_RUNNING.value}
        }

        count = 0

        def fake_get_deployment(tool_name: str, deployment_name: str) -> Deployment:
            nonlocal count
            # 3 is the magic number here, so it gets to start the build before cancelling
            if count == 3:
                my_deployment.status = DeploymentState.cancelling
            else:
                count += 1
            return my_deployment

        monkeypatch.setattr(my_storage, "get_deployment", fake_get_deployment)

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.cancelled,
                        build_long_status="You can see the logs with `toolforge build logs my-build`",
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.skipped,
                        run_long_status="The deployment was cancelled",
                    )
                },
                tool_config=get_tool_config(),
                status=DeploymentState.cancelled,
                long_status="Deployment was cancelled",
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
            runtime=get_runtime(settings=get_settings()),
        )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        assert gotten_deployments == expected_deployments
        toolforge_client_mock.patch.assert_not_called()

    def test_parses_jobs_api_http_error_messages_when_run_fails(
        self, monkeypatch: MonkeyPatch
    ):
        my_storage = MockStorage()
        my_tool_config = get_tool_config()
        my_deployment = get_deployment_from_tool_config(tool_config=my_tool_config)
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.runtime.toolforge.get_toolforge_client",
            lambda: toolforge_client_mock,
        )
        toolforge_client_mock.post.return_value = {"new_build": {"name": "my-build"}}
        toolforge_client_mock.get.return_value = {
            "build": {"status": BuildsBuildStatus.BUILD_SUCCESS}
        }
        # Fake a bad request error from jobs-api
        http_error = requests.exceptions.HTTPError(
            "Bad request", response=requests.Response()
        )
        # Gotten from a request from lima-kilo
        # >>> response = requests.post("https://127.0.0.1:30003/jobs/v1/tool/tf-test/jobs", cert=("/data/project/tf-test/.toolskube/client.crt", "/data/project/tf-test/.toolskube/client.key"), json='{"fooo": 111}', verify=False)
        # >>> try:
        # ...    response.raise_for_status()
        # ... except Exception as error:
        # ...     myerr = error
        # ...
        # >>> myerr.response.content
        # b'{"error":["1 validation error for NewJob\\n  Input should be a valid dictionary or instance of NewJob [type=model_type, input_value=\'{\\"fooo\\": 111}\', input_type=str]"]}\
        http_error.response._content = b'{"error":["Ayayayay!"]}\n'
        http_error.response.status_code = status.HTTP_400_BAD_REQUEST
        http_error.response.url = "/bad/bad/url"
        toolforge_client_mock.patch.side_effect = [http_error]

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.successful,
                        build_long_status="You can see the logs with `toolforge build logs my-build`",
                    ),
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.failed,
                        run_long_status="Bad request (400): Ayayayay!",
                    ),
                },
                tool_config=get_tool_config(),
                status=DeploymentState.failed,
                long_status="I will not be checked",
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
            runtime=get_runtime(settings=get_settings()),
        )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        expected_deployments[0].long_status = gotten_deployments[0].long_status
        assert gotten_deployments == expected_deployments
        toolforge_client_mock.patch.assert_called_once_with(
            "/jobs/v1/tool/my-tool/jobs/",
            json={
                "job_type": "continuous",
                "cmd": "my-command",
                "name": "my-component",
                "imagename": "tool-my-tool/my-component:latest",
            },
            verify=True,
        )

    def test_reruns_job_even_if_config_did_not_change_and_build_skipped_if_force_run_passed(
        self, monkeypatch: MonkeyPatch
    ):
        my_storage = MockStorage()
        my_tool_config = get_tool_config()
        my_deployment = get_deployment_from_tool_config(
            tool_config=my_tool_config, force_run=True
        )
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        monkeypatch.setattr(
            "components.runtime.toolforge._resolve_ref",
            lambda *args, **kwargs: "same-ref-as-build",
        )
        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.runtime.toolforge.get_toolforge_client",
            lambda: toolforge_client_mock,
        )
        toolforge_client_mock.post.return_value = {"new_build": {"name": "my-build"}}
        toolforge_client_mock.get.side_effect = [
            {
                "builds": [
                    {
                        "build_id": "existing-build-id",
                        "name": "my-component",
                        "resolved_ref": "same-ref-as-build",
                        "destination_image": "my-tool/my-component:latest",
                        "status": BuildsBuildStatus.BUILD_SUCCESS.value,
                        "parameters": {
                            "image_name": "my-component",
                            "source_url": "my-url",
                        },
                    }
                ]
            },
            JobsJobListResponse(jobs=[get_defined_job(name="my-component")]),
        ]
        toolforge_client_mock.delete.return_value = JobsJobResponse().model_dump()
        toolforge_client_mock.patch.return_value = JobsJobResponse(
            messages=JobsResponseMessages(
                error=None, info=["created continuous job my-job-name"], warning=None
            )
        ).model_dump()

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="existing-build-id",
                        build_status=DeploymentBuildState.skipped,
                        build_long_status="Reusing existing build",
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.successful,
                        run_long_status="[info] (created continuous job my-job-name)",
                    )
                },
                tool_config=get_tool_config(),
                status=DeploymentState.successful,
                long_status="I will not be checked",
                force_run=True,
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
            runtime=get_runtime(settings=get_settings()),
        )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        expected_deployments[0].long_status = gotten_deployments[0].long_status
        assert gotten_deployments == expected_deployments
        toolforge_client_mock.patch.assert_called_with(
            "/jobs/v1/tool/my-tool/jobs/",
            json={
                "job_type": "continuous",
                "cmd": "my-command",
                "name": "my-component",
                "imagename": "tool-my-tool/my-component:latest",
            },
            verify=True,
        )
        toolforge_client_mock.delete.assert_called_with(
            "/jobs/v1/tool/my-tool/jobs/my-component", verify=True
        )

    def test_reruns_job_even_if_config_did_not_change_and_force_run_not_passed_if_build_ran(
        self, monkeypatch: MonkeyPatch
    ):
        my_storage = MockStorage()
        my_tool_config = get_tool_config()
        my_deployment = get_deployment_from_tool_config(
            tool_config=my_tool_config, force_run=False
        )
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.runtime.toolforge.get_toolforge_client",
            lambda: toolforge_client_mock,
        )
        toolforge_client_mock.post.return_value = {"new_build": {"name": "my-build"}}
        toolforge_client_mock.get.side_effect = [
            {"build": {"status": BuildsBuildStatus.BUILD_SUCCESS}},
            {"build": {"status": BuildsBuildStatus.BUILD_SUCCESS}},
            JobsJobListResponse(jobs=[get_defined_job(name="my-component")]),
        ]
        toolforge_client_mock.delete.return_value = JobsJobResponse().model_dump()
        toolforge_client_mock.patch.return_value = JobsJobResponse(
            messages=JobsResponseMessages(
                error=None, info=["created continuous job my-job-name"], warning=None
            )
        ).model_dump()

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.successful,
                        build_long_status="You can see the logs with `toolforge build logs my-build`",
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.successful,
                        run_long_status="[info] (created continuous job my-job-name)",
                    )
                },
                tool_config=get_tool_config(),
                status=DeploymentState.successful,
                long_status="I will not be checked",
                force_run=False,
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
            runtime=get_runtime(settings=get_settings()),
        )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        expected_deployments[0].long_status = gotten_deployments[0].long_status
        assert gotten_deployments == expected_deployments
        toolforge_client_mock.patch.assert_called_with(
            "/jobs/v1/tool/my-tool/jobs/",
            json={
                "job_type": "continuous",
                "cmd": "my-command",
                "name": "my-component",
                "imagename": "tool-my-tool/my-component:latest",
            },
            verify=True,
        )
        toolforge_client_mock.delete.assert_called_with(
            "/jobs/v1/tool/my-tool/jobs/my-component", verify=True
        )

    def test_reruns_job_for_reused_components_when_build_changed(
        self, monkeypatch: MonkeyPatch
    ):
        my_storage = MockStorage()
        my_tool_config = ToolConfig(
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
                ),
                "first-component": ContinuousComponentInfo(
                    build=SourceBuildReference(
                        reuse_from="my-component",
                    ),
                    run=ContinuousRunInfo(
                        command="my-second-command",
                    ),
                ),
                "second-component": ContinuousComponentInfo(
                    build=SourceBuildReference(
                        reuse_from="my-component",
                    ),
                    run=ContinuousRunInfo(
                        command="my-third-command",
                    ),
                ),
            },
        )
        my_deployment = get_deployment_from_tool_config(tool_config=my_tool_config)
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.runtime.toolforge.get_toolforge_client",
            lambda: toolforge_client_mock,
        )
        toolforge_client_mock.post.return_value = {"new_build": {"name": "my-build"}}

        # This needs to be parseable in `_do_run` or we skip the restart logic block,
        # which makes everything always created, making this test redundant.
        def _mock_get_side_effect(path: str, *args, **kwargs):
            # Jobs
            if path == "/jobs/v1/tool/my-tool/jobs":
                return {
                    "jobs": [
                        get_defined_job(name="my-component"),
                        get_defined_job(name="first-component"),
                        get_defined_job(name="second-component"),
                    ]
                }

            # Build
            return {"build": {"status": BuildsBuildStatus.BUILD_SUCCESS.value}}

        toolforge_client_mock.get = _mock_get_side_effect

        toolforge_client_mock.patch.return_value = JobsJobResponse().model_dump()

        toolforge_client_mock.delete.return_value = JobsJobResponse().model_dump()

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
            runtime=get_runtime(settings=get_settings()),
        )

        toolforge_client_mock.delete.assert_has_calls(
            [
                call("/jobs/v1/tool/my-tool/jobs/my-component", verify=True),
                call("/jobs/v1/tool/my-tool/jobs/first-component", verify=True),
                call("/jobs/v1/tool/my-tool/jobs/second-component", verify=True),
            ],
            any_order=True,
        )

    def test_starts_build_and_reused_image_for_second_component(
        self, monkeypatch: MonkeyPatch
    ):
        my_storage = MockStorage()
        my_tool_config = ToolConfig(
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
                ),
                "child-component": ContinuousComponentInfo(
                    build=SourceBuildReference(
                        reuse_from="my-component",
                    ),
                    run=ContinuousRunInfo(
                        command="my-second-command",
                    ),
                ),
            },
        )
        my_deployment = get_deployment_from_tool_config(tool_config=my_tool_config)
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.runtime.toolforge.get_toolforge_client",
            lambda: toolforge_client_mock,
        )
        toolforge_client_mock.post.return_value = {"new_build": {"name": "my-build"}}
        toolforge_client_mock.get.return_value = {
            "build": {"status": BuildsBuildStatus.BUILD_SUCCESS.value}
        }
        toolforge_client_mock.patch.return_value = JobsJobResponse(
            messages=JobsResponseMessages(
                error=None, info=["created continuous job my-job-name"], warning=None
            ),
        ).model_dump()

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="my-build",
                        build_status=DeploymentBuildState.successful,
                        build_long_status="You can see the logs with `toolforge build logs my-build`",
                    ),
                    "child-component": DeploymentBuildInfo(
                        build_id="no-build-needed",
                        build_status=DeploymentBuildState.skipped,
                        build_long_status="Component re-uses build from my-component",
                    ),
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.successful,
                        run_long_status="[info] (created continuous job my-job-name)",
                    ),
                    "child-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.successful,
                        run_long_status="[info] (created continuous job my-job-name)",
                    ),
                },
                tool_config=my_tool_config,
                status=DeploymentState.successful,
                long_status="I will not be checked",
            )
        ]

        do_deploy(
            deployment=my_deployment,
            storage=my_storage,
            tool_config=my_tool_config,
            tool_name="my-tool",
            runtime=get_runtime(settings=get_settings()),
        )

        gotten_deployments = my_storage.list_deployments(tool_name="my-tool")

        # make sure that we have some deployments
        assert gotten_deployments
        expected_deployments[0].long_status = gotten_deployments[0].long_status
        assert gotten_deployments == expected_deployments

        toolforge_client_mock.patch.assert_has_calls(
            [
                call(
                    "/jobs/v1/tool/my-tool/jobs/",
                    json={
                        "job_type": "continuous",
                        "cmd": "my-command",
                        "name": "my-component",
                        "imagename": "tool-my-tool/my-component:latest",
                    },
                    verify=True,
                ),
                call(
                    "/jobs/v1/tool/my-tool/jobs/",
                    json={
                        "job_type": "continuous",
                        "cmd": "my-second-command",
                        "name": "child-component",
                        "imagename": "tool-my-tool/my-component:latest",
                    },
                    verify=True,
                ),
            ],
            any_order=True,
        )


class TestExceptionRetry:
    def test_raises_on_non_http_error(self):
        def _func():
            raise ValueError("the unicorns are busy")

        with pytest.raises(ValueError):
            _retry_http_failures(_func)()

    def test_returns_on_success(self):
        def _func():
            return "Pink Pony Club"

        _retry_http_failures(_func)()

    def test_raises_after_retries(self):
        def _func():
            raise ReadTimeout("the unicorns are busy")

        with pytest.raises(ReadTimeout) as exc_info:
            _retry_http_failures(_func)()

        assert isinstance(exc_info.value, ReadTimeout)
