import logging
from typing import Any

import kubernetes  # type: ignore
from fastapi import status

from ..models.api_models import Deployment, DeploymentToken, ToolConfig
from .base import Storage
from .exceptions import NotFoundInStorage, StorageError

logger = logging.getLogger(__name__)


def _tool_config_to_k8s_crd(tool_name: str, tool_config: ToolConfig) -> dict[str, Any]:
    k8s_dict = {
        "kind": "ToolConfig",
        "apiVersion": "toolforge.org/v1",
        "metadata": {"name": _get_k8s_tool_config_name(tool_name)},
        "spec": tool_config.model_dump(mode="json"),
    }
    return k8s_dict


def _deployment_to_k8s_crd(tool_name: str, deployment: Deployment) -> dict[str, Any]:
    k8s_dict = {
        "kind": "ToolDeployment",
        "apiVersion": "toolforge.org/v1",
        "metadata": {"name": deployment.deploy_id},
        "spec": deployment.model_dump(mode="json"),
    }
    return k8s_dict


def _get_k8s_tool_config_name(tool_name: str) -> str:
    return f"{tool_name}-config"


def _get_k8s_tool_namespace(tool_name: str) -> str:
    return f"tool-{tool_name}"


class KubernetesStorage(Storage):
    def __init__(self) -> None:
        # this tries out of cluster first, then in-cluster
        kubernetes.config.load_config()
        # we only need the crds API, only using it as storage
        self.k8s = kubernetes.client.CustomObjectsApi()

    def get_tool_config(self, tool_name: str) -> ToolConfig:
        namespace = _get_k8s_tool_namespace(tool_name=tool_name)
        config_name = _get_k8s_tool_config_name(tool_name)
        try:
            k8s_tool_config = self.k8s.get_namespaced_custom_object(
                group="toolforge.org",
                version="v1",
                name=config_name,
                plural="toolconfigs",
                namespace=namespace,
            )
        except kubernetes.client.ApiException as error:
            logger.exception(
                f"Attempted to get tool config for tool:{tool_name} in namespace:{namespace}"
            )
            if error.status == status.HTTP_404_NOT_FOUND:
                raise NotFoundInStorage(
                    f"Unable to find namespace {namespace} or config {config_name} for {tool_name}"
                ) from error

            raise StorageError(
                f"Got unexpected error when trying to load config for {tool_name}"
            ) from error

        return ToolConfig.model_validate(k8s_tool_config["spec"])

    def set_tool_config(self, tool_name: str, config: ToolConfig) -> None:
        try:
            self._create_tool_config(tool_name=tool_name, config=config)
        except kubernetes.client.ApiException as error:
            if error.status == status.HTTP_409_CONFLICT:
                # it already exists, just update
                self._delete_tool_config(tool_name=tool_name)
                self._create_tool_config(tool_name=tool_name, config=config)

    def delete_tool_config(self, tool_name: str) -> ToolConfig:
        old_tool_config = self.get_tool_config(tool_name=tool_name)
        self._delete_tool_config(tool_name=tool_name)
        return old_tool_config

    def _create_tool_config(self, tool_name: str, config: ToolConfig) -> None:
        namespace = _get_k8s_tool_namespace(tool_name=tool_name)
        body = _tool_config_to_k8s_crd(tool_config=config, tool_name=tool_name)
        try:
            self.k8s.create_namespaced_custom_object(
                group="toolforge.org",
                version="v1",
                plural="toolconfigs",
                namespace=namespace,
                body=body,
            )
        except kubernetes.client.ApiException as error:
            if error.status == status.HTTP_409_CONFLICT:
                # bubble up for us to handle
                raise

            logger.exception(
                f"Attempted to create tool config for tool:{tool_name} in namespace:{namespace} with body: {body}"
            )
            if error.status == status.HTTP_404_NOT_FOUND:
                raise NotFoundInStorage(
                    f"Unable to find namespace {namespace} for tool {tool_name}"
                ) from error

            raise StorageError(
                f"Got unexpected error ({error}) when trying to create config for {tool_name}"
            ) from error

    def _delete_tool_config(self, tool_name: str) -> None:
        namespace = _get_k8s_tool_namespace(tool_name=tool_name)
        config_name = _get_k8s_tool_config_name(tool_name)
        try:
            # delete and recreate to avoid having to figure out what to patch
            self.k8s.delete_namespaced_custom_object(
                group="toolforge.org",
                version="v1",
                plural="toolconfigs",
                namespace=namespace,
                name=config_name,
            )
        except kubernetes.client.ApiException as error:
            logger.exception(
                f"Attempted to delete tool config for tool:{tool_name} in namespace:{namespace}"
            )
            if error.status == status.HTTP_404_NOT_FOUND:
                raise NotFoundInStorage(
                    f"Unable to find namespace {namespace} or config {config_name} for {tool_name}"
                ) from error

            raise StorageError(
                f"Got unexpected error when trying to delete config for {tool_name}"
            ) from error

    def get_deployment(self, tool_name: str, deployment_name: str) -> Deployment:
        namespace = _get_k8s_tool_namespace(tool_name=tool_name)
        try:
            k8s_deployment = self.k8s.get_namespaced_custom_object(
                group="toolforge.org",
                version="v1",
                name=deployment_name,
                plural="tooldeployments",
                namespace=namespace,
            )
        except kubernetes.client.ApiException as error:
            if error.status == status.HTTP_404_NOT_FOUND:
                raise NotFoundInStorage(
                    f"Unable to find namespace {namespace} or deployment {deployment_name} for {tool_name}"
                ) from error

            raise StorageError(
                f"Got unexpected error when trying to load deployment for {tool_name}"
            ) from error

        return Deployment.model_validate(k8s_deployment["spec"])

    def create_deployment(self, tool_name: str, deployment: Deployment) -> None:
        namespace = _get_k8s_tool_namespace(tool_name=tool_name)
        body = _deployment_to_k8s_crd(deployment=deployment, tool_name=tool_name)
        try:
            self.k8s.create_namespaced_custom_object(
                group="toolforge.org",
                version="v1",
                plural="tooldeployments",
                namespace=namespace,
                body=body,
            )
        except kubernetes.client.ApiException as error:
            if error.status == status.HTTP_404_NOT_FOUND:
                raise NotFoundInStorage(
                    f"Unable to find namespace {namespace} for tool {tool_name}"
                ) from error

            raise StorageError(
                f"Got unexpected error ({error}) when trying to create deployment for {tool_name}"
            ) from error

    def get_deployment_token(self, tool_name: str) -> DeploymentToken:
        raise NotImplementedError

    def create_deployment_token(self, tool_name: str) -> DeploymentToken:
        raise NotImplementedError

    def delete_deployment_token(self, tool_name: str) -> None:
        raise NotImplementedError
