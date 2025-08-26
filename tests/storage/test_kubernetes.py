import datetime
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time
from pytest import MonkeyPatch

from components.models.api_models import DeploymentState
from components.settings import get_settings
from components.storage.kubernetes import KubernetesStorage

from ..testlibs import get_deployment_from_tool_config, get_tool_config


class TestKubernetesStorage:
    @pytest.mark.parametrize(
        "storage_func",
        [
            "create_deployment",
            "update_deployment",
        ],
    )
    def test_create_and_update_time_out_old_deployments(
        self,
        storage_func: str,
        storage_k8s_cli: MagicMock,
        monkeypatch: MonkeyPatch,
    ):
        """This is needed to ensure the specific _timeout_old_deployment tests are valid."""
        storage_k8s_cli.get_namespaced_custom_object.return_value = {
            "spec": get_deployment_from_tool_config(
                tool_config=get_tool_config()
            ).model_dump()
        }

        timeout_old_deployments_mock = MagicMock(
            spec=KubernetesStorage._timeout_old_deployments
        )
        monkeypatch.setattr(
            "components.storage.kubernetes.KubernetesStorage._timeout_old_deployments",
            timeout_old_deployments_mock,
        )
        storage = KubernetesStorage()
        getattr(storage, storage_func)(
            deployment=get_deployment_from_tool_config(tool_config=get_tool_config()),
            tool_name="my-tool",
        )

        assert len(timeout_old_deployments_mock.mock_calls) == 1

    @pytest.mark.parametrize(
        "storage_func",
        [
            "get_deployment",
            "delete_deployment",
        ],
    )
    def test_delete_and_get_time_out_old_deployments(
        self,
        storage_func: str,
        storage_k8s_cli: MagicMock,
        monkeypatch: MonkeyPatch,
    ):
        """This is needed to ensure the specific _timeout_old_deployment tests are valid."""
        storage_k8s_cli.get_namespaced_custom_object.return_value = {
            "spec": get_deployment_from_tool_config(
                tool_config=get_tool_config()
            ).model_dump()
        }

        timeout_old_deployments_mock = MagicMock(
            spec=KubernetesStorage._timeout_old_deployments
        )
        monkeypatch.setattr(
            "components.storage.kubernetes.KubernetesStorage._timeout_old_deployments",
            timeout_old_deployments_mock,
        )
        storage = KubernetesStorage()
        getattr(storage, storage_func)(
            deployment_name=get_deployment_from_tool_config(
                tool_config=get_tool_config()
            ).deploy_id,
            tool_name="my-tool",
        )

        assert len(timeout_old_deployments_mock.mock_calls) == 1

    def test_list_deployments_time_out_old_deployments(
        self,
        storage_k8s_cli: MagicMock,
        monkeypatch: MonkeyPatch,
    ):
        """This is needed to ensure the specific _timeout_old_deployment tests are valid."""
        storage_k8s_cli.get_namespaced_custom_object.return_value = {
            "spec": get_deployment_from_tool_config(
                tool_config=get_tool_config()
            ).model_dump()
        }

        timeout_old_deployments_mock = MagicMock(
            spec=KubernetesStorage._timeout_old_deployments
        )
        monkeypatch.setattr(
            "components.storage.kubernetes.KubernetesStorage._timeout_old_deployments",
            timeout_old_deployments_mock,
        )
        storage = KubernetesStorage()
        storage.list_deployments(tool_name="my-tool")

        assert len(timeout_old_deployments_mock.mock_calls) == 1


class TestTimeoutOldDeployments:
    def test_times_out_old_deployment_but_not_new(self, storage_k8s_cli: MagicMock):
        storage = KubernetesStorage()
        old_deployment = get_deployment_from_tool_config(
            tool_config=get_tool_config(), creation_time="20210601-000000"
        )
        new_deployment = get_deployment_from_tool_config(
            tool_config=get_tool_config(), creation_time="20550602-000000"
        )
        storage._list_deployments = MagicMock(spec=storage._list_deployments)
        storage._list_deployments.return_value = [old_deployment, new_deployment]
        storage._update_deployment = MagicMock(spec=storage._update_deployment)

        storage._timeout_old_deployments(tool_name="my-tool")

        storage._update_deployment.assert_called_once_with(
            deployment=old_deployment, tool_name="my-tool"
        )

    def test_times_out_old_deployment_after_a_bit_more_than_config(
        self, storage_k8s_cli: MagicMock
    ):
        storage = KubernetesStorage()
        settings = get_settings()
        cur_date = datetime.datetime.now()
        old_deployment = get_deployment_from_tool_config(
            tool_config=get_tool_config(),
            creation_time=cur_date.strftime("%Y%m%d-%H%M%S"),
        )
        storage._list_deployments = MagicMock(spec=storage._list_deployments)
        storage._list_deployments.return_value = [old_deployment]
        storage._update_deployment = MagicMock(spec=storage._update_deployment)

        with freeze_time(
            cur_date + settings.deployment_timeout + datetime.timedelta(seconds=1)
        ):
            storage._timeout_old_deployments(tool_name="my-tool")

        storage._update_deployment.assert_called_once_with(
            deployment=old_deployment, tool_name="my-tool"
        )

    @pytest.mark.parametrize(
        "deployment_state",
        [
            DeploymentState.pending,
            DeploymentState.running,
        ],
    )
    def test_times_out_active_deployments(
        self, deployment_state: DeploymentState, storage_k8s_cli: MagicMock
    ):
        storage = KubernetesStorage()
        deployment_to_time_out = get_deployment_from_tool_config(
            tool_config=get_tool_config(),
            with_deployment_state=deployment_state,
            creation_time="20210601-000000",
        )
        storage._list_deployments = MagicMock(spec=storage._list_deployments)
        storage._list_deployments.return_value = [deployment_to_time_out]
        storage._update_deployment = MagicMock(spec=storage._update_deployment)

        storage._timeout_old_deployments(tool_name="my-tool")

        storage._update_deployment.assert_called_once_with(
            deployment=deployment_to_time_out, tool_name="my-tool"
        )

    @pytest.mark.parametrize(
        "deployment_state",
        [
            DeploymentState.failed,
            DeploymentState.successful,
            DeploymentState.timed_out,
        ],
    )
    def test_does_not_time_out_inactive_deployments(
        self, deployment_state: DeploymentState, storage_k8s_cli: MagicMock
    ):
        storage = KubernetesStorage()
        deployment_to_ignore = get_deployment_from_tool_config(
            tool_config=get_tool_config(),
            with_deployment_state=deployment_state,
            creation_time="20210601-000000",
        )
        storage._list_deployments = MagicMock(spec=storage._list_deployments)
        storage._list_deployments.return_value = [deployment_to_ignore]
        storage._update_deployment = MagicMock(spec=storage._update_deployment)

        storage._timeout_old_deployments(tool_name="my-tool")

        storage._update_deployment.assert_not_called()
