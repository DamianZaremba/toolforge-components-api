import datetime
from unittest.mock import MagicMock

import pytest
import requests
from fastapi import status
from freezegun import freeze_time
from pytest import MonkeyPatch
from toolforge_weld.api_client import ToolforgeClient

from components.deploy_task import do_deploy
from components.gen.toolforge_models import (
    BuildsBuildStatus,
    JobsJobListResponse,
    JobsJobResponse,
    JobsResponseMessages,
)
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

from .testlibs import get_defined_job, get_deployment_from_tool_config, get_tool_config


class TestDoDeploy:
    @pytest.mark.parametrize(
        "existing_build_start_status, expected_build_status",
        [
            [BuildsBuildStatus.BUILD_PENDING, DeploymentBuildState.successful],
            [BuildsBuildStatus.BUILD_RUNNING, DeploymentBuildState.successful],
            [BuildsBuildStatus.BUILD_SUCCESS, DeploymentBuildState.skipped],
        ],
    )
    def test_skip_build_if_no_change_in_ref_hash_and_existing_build(
        self,
        monkeypatch: MonkeyPatch,
        existing_build_start_status: BuildsBuildStatus,
        expected_build_status: DeploymentBuildState,
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

        monkeypatch.setattr(
            "components.deploy_task._resolve_ref",
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
        ]
        toolforge_client_mock.post.return_value = {
            "new_build": {"name": "my-component"}
        }
        toolforge_client_mock.patch.return_value = JobsJobResponse(
            job=get_defined_job(), messages=None
        ).model_dump()

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id=existing_build_id,
                        build_status=expected_build_status,
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.successful,
                        run_long_status="created continuous job my-job-name",
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
            "components.deploy_task.get_toolforge_client",
            lambda: toolforge_client_mock,
        )

        monkeypatch.setattr(
            "components.deploy_task._resolve_ref",
            lambda *args, **kwargs: "same-ref-as-build",
        )

        toolforge_client_mock.post.return_value = {
            "new_build": {"name": "new_build_name"}
        }
        toolforge_client_mock.get.return_value = {
            "build": {"status": BuildsBuildStatus.BUILD_SUCCESS}
        }
        toolforge_client_mock.patch.return_value = JobsJobResponse(
            job=get_defined_job(), messages=None
        ).model_dump()

        expected_deployments = [
            Deployment(
                deploy_id="my-deploy-id",
                creation_time="2021-06-01T00:00:00",
                builds={
                    "my-component": DeploymentBuildInfo(
                        build_id="new_build_name",
                        build_status=DeploymentBuildState.successful,
                    )
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.successful,
                        run_long_status="created continuous job my-job-name",
                    )
                },
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
        toolforge_client_mock.patch.return_value = JobsJobResponse(
            job=get_defined_job(), messages=None
        ).model_dump()

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
                        run_long_status="created continuous job my-job-name",
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
                        run_status=DeploymentRunState.skipped,
                        run_long_status="Skipped due to previous failure",
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
                        run_status=DeploymentRunState.skipped,
                        run_long_status="Skipped due to previous failure",
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
                        run_status=DeploymentRunState.skipped,
                        run_long_status="Skipped due to previous failure",
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
                        run_long_status="Ayayayay!",
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
                        run_long_status="Ayayayay!",
                    ),
                    "successful-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.skipped,
                        run_long_status="Skipped due to previous failure",
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

    def test_parses_jobs_api_http_error_messages_when_run_fails(
        self, monkeypatch: MonkeyPatch
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
                    ),
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.failed,
                        run_long_status="Bad request (400): Ayayayay!",
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
        toolforge_client_mock.patch.assert_called_once_with(
            "/jobs/v1/tool/my-tool/jobs/",
            json={
                "cmd": "my-command",
                "continuous": True,
                "name": "my-component",
                "imagename": "tool-my-tool/my-component:latest",
            },
            verify=True,
        )

    def test_parses_jobs_api_http_error_messages_when_run_works_but_no_job_name_returned(
        self, monkeypatch: MonkeyPatch
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
            "build": {"status": BuildsBuildStatus.BUILD_SUCCESS}
        }
        toolforge_client_mock.patch.return_value = JobsJobResponse(
            job=None,
            messages=JobsResponseMessages(
                error=None, info=["Job component1 is already up to date"], warning=None
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
                    ),
                },
                runs={
                    "my-component": DeploymentRunInfo(
                        run_status=DeploymentRunState.successful,
                        run_long_status="[info] (Job component1 is already up to date)",
                    ),
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
        toolforge_client_mock.patch.assert_called_once_with(
            "/jobs/v1/tool/my-tool/jobs/",
            json={
                "cmd": "my-command",
                "continuous": True,
                "name": "my-component",
                "imagename": "tool-my-tool/my-component:latest",
            },
            verify=True,
        )

    def test_reruns_job_even_if_config_did_not_change_if_force_run_passed(
        self, monkeypatch: MonkeyPatch
    ):
        my_storage = MockStorage()
        my_tool_config = get_tool_config()
        my_deployment = get_deployment_from_tool_config(
            tool_config=my_tool_config, force_run=True
        )
        my_storage.create_deployment(tool_name="my-tool", deployment=my_deployment)

        toolforge_client_mock = MagicMock(spec=ToolforgeClient)
        monkeypatch.setattr(
            "components.deploy_task.get_toolforge_client",
            lambda: toolforge_client_mock,
        )
        toolforge_client_mock.post.return_value = {"new_build": {"name": "my-build"}}
        toolforge_client_mock.get.side_effect = [
            {"build": {"status": BuildsBuildStatus.BUILD_SUCCESS}},
            {"build": {"status": BuildsBuildStatus.BUILD_SUCCESS}},
            JobsJobListResponse(jobs=[get_defined_job(name="my-component")]),
        ]
        toolforge_client_mock.delete.return_value = {
            "messages": {"info": [], "warning": [], "error": []}
        }
        toolforge_client_mock.patch.return_value = JobsJobResponse(
            job=get_defined_job(name="my-component")
        )

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
                        run_long_status="created continuous job my-component",
                    )
                },
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
        toolforge_client_mock.delete.assert_called_with(
            "/jobs/v1/tool/my-tool/jobs/my-component", verify=True
        )
