import logging
from typing import Any

import kubernetes  # type: ignore
from fastapi import status
from requests.exceptions import HTTPError

from ..client import get_toolforge_client
from ..gen.toolforge_models import (
    EnvvarsEnvvar,
    EnvvarsEnvvarName,
    EnvvarsGetResponse,
)
from ..models.api_models import Deployment, DeployToken, ToolConfig
from ..settings import get_settings
from .base import Storage
from .exceptions import NotFoundInStorage, StorageError

logger = logging.getLogger(__name__)

DEPLOY_TOKEN_ENVVAR = "TOOL_DEPLOY_TOKEN"


def _tool_config_to_k8s_crd(tool_name: str, tool_config: ToolConfig) -> dict[str, Any]:
    k8s_dict = {
        "kind": "ToolConfig",
        "apiVersion": "toolforge.org/v1",
        "metadata": {"name": _get_k8s_tool_config_name(tool_name)},
        "spec": tool_config.model_dump(mode="json"),
    }
    return k8s_dict


def _deploy_to_k8s_crd(tool_name: str, deployment: Deployment) -> dict[str, Any]:
    k8s_dict = {
        "kind": "ToolDeployment",
        "apiVersion": "toolforge.org/v1",
        "metadata": {"name": deployment.deploy_id},
        "spec": deployment.model_dump(mode="json"),
    }
    return k8s_dict


def _deploy_token_to_k8s_crd(tool_name: str, token: DeployToken) -> dict[str, Any]:
    k8s_dict = {
        "kind": "DeployToken",
        "apiVersion": "toolforge.org/v1",
        "metadata": {"name": tool_name},
        "spec": token.model_dump(mode="json"),
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
        self.toolforge_client = get_toolforge_client()

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
            else:
                raise Exception(
                    "Unexpected unhandled k8s ApiException, should not have reached here."
                ) from error

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
        body = _deploy_to_k8s_crd(deployment=deployment, tool_name=tool_name)
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

    def _delete_deployment(self, tool_name: str, deployment_name: str) -> None:
        namespace = _get_k8s_tool_namespace(tool_name=tool_name)
        try:
            self.k8s.delete_namespaced_custom_object(
                group="toolforge.org",
                version="v1",
                plural="tooldeployments",
                namespace=namespace,
                name=deployment_name,
            )
        except kubernetes.client.ApiException as error:
            logger.exception(
                f"Attempted to delete deployment for tool:{tool_name} in namespace:{namespace}"
            )
            if error.status == status.HTTP_404_NOT_FOUND:
                raise NotFoundInStorage(
                    f"Unable to find namespace {namespace} or deployment {deployment_name} for {tool_name}"
                ) from error

            raise StorageError(
                f"Got unexpected error when trying to delete deployment for {tool_name}"
            ) from error

    def delete_deployment(self, tool_name: str, deployment_name: str) -> Deployment:
        deployment = self.get_deployment(tool_name, deployment_name)
        self._delete_deployment(tool_name, deployment_name)
        return deployment

    def get_deploy_token(self, tool_name: str) -> DeployToken:
        namespace = _get_k8s_tool_namespace(tool_name=tool_name)
        try:
            k8s_token = self.k8s.get_namespaced_custom_object(
                group="toolforge.org",
                version="v1",
                name=tool_name,
                plural="deploytokens",
                namespace=namespace,
            )
        except kubernetes.client.ApiException as error:
            if error.status == status.HTTP_404_NOT_FOUND:
                raise NotFoundInStorage(
                    f"Unable to find namespace {namespace} or deploytoken {tool_name} for {tool_name}"
                ) from error

            raise StorageError(
                f"Got unexpected error when trying to load deploy token for {tool_name}"
            ) from error

        return DeployToken.model_validate(k8s_token["spec"])

    def _set_deploy_token_envvar(self, tool_name: str, token: DeployToken) -> None:
        settings = get_settings()

        envvar = EnvvarsEnvvar(
            name=EnvvarsEnvvarName(DEPLOY_TOKEN_ENVVAR),
            value=str(token.token),
        )

        try:
            response_data = self.toolforge_client.post(
                f"/envvars/v1/tool/{tool_name}/envvars",
                json=envvar.model_dump(mode="json", exclude_none=True),
                verify=settings.verify_toolforge_api_cert,
            )
            response = EnvvarsGetResponse.model_validate(response_data)
            logger.debug(f"Deploy token set for tool: {tool_name}: {response}")
        except Exception as error:
            logger.error(
                f"Error setting deploy token for tool {tool_name}: {str(error)}"
            )
            raise StorageError(
                f"Got unexpected error when trying to set deploy token for {tool_name}"
            ) from error

    def _set_deploy_token_crd(self, tool_name: str, token: DeployToken) -> None:
        namespace = _get_k8s_tool_namespace(tool_name=tool_name)
        body = _deploy_token_to_k8s_crd(token=token, tool_name=tool_name)
        try:
            self.k8s.create_namespaced_custom_object(
                group="toolforge.org",
                version="v1",
                plural="deploytokens",
                namespace=namespace,
                body=body,
            )
        except kubernetes.client.ApiException as error:
            if error.status == status.HTTP_404_NOT_FOUND:
                raise NotFoundInStorage(
                    f"Unable to find namespace {namespace} for tool {tool_name}"
                ) from error

            if error.status == status.HTTP_409_CONFLICT:
                # bubble up for us to handle
                raise error

            raise StorageError(
                f"Got unexpected error ({error}) when trying to create deploy token for {tool_name}"
            ) from error

    def set_deploy_token(self, tool_name: str, token: DeployToken) -> None:
        try:
            self._set_deploy_token_crd(tool_name=tool_name, token=token)
        except kubernetes.client.ApiException as error:
            if error.status == status.HTTP_409_CONFLICT:
                self._delete_deploy_token_crd(tool_name=tool_name)
                self._set_deploy_token_crd(tool_name=tool_name, token=token)
            else:
                raise Exception(
                    "Unexpected unhandled k8s ApiException, should not have reached here."
                ) from error

        self._set_deploy_token_envvar(tool_name=tool_name, token=token)

    def _delete_deploy_token_envvar(self, tool_name: str) -> None:
        settings = get_settings()

        try:
            self.toolforge_client.delete(
                f"/envvars/v1/tool/{tool_name}/envvars/{DEPLOY_TOKEN_ENVVAR}",
                verify=settings.verify_toolforge_api_cert,
            )
            logger.info(f"Deploy token deleted for tool: {tool_name}")
        except HTTPError as http_err:
            logger.error(
                f"HTTP error occurred while deleting deploy token for tool {tool_name}: {http_err}"
            )
            raise StorageError(
                f"Failed to delete deploy token for tool {tool_name}: {http_err}"
            ) from http_err
        except Exception as error:
            logger.error(
                f"Unexpected error occurred while deleting deploy token for tool {tool_name}: {error}"
            )
            raise StorageError(
                f"Unexpected error when trying to delete deploy token for tool {tool_name}"
            ) from error

    def _delete_deploy_token_crd(self, tool_name: str) -> None:
        namespace = _get_k8s_tool_namespace(tool_name=tool_name)
        token_name = tool_name
        try:
            # delete and recreate to avoid having to figure out what to patch
            self.k8s.delete_namespaced_custom_object(
                group="toolforge.org",
                version="v1",
                plural="deploytokens",
                namespace=namespace,
                name=token_name,
            )
        except kubernetes.client.ApiException as error:
            logger.exception(
                f"Attempted to delete deploy token for tool:{tool_name} in namespace:{namespace}"
            )
            if error.status == status.HTTP_404_NOT_FOUND:
                raise NotFoundInStorage(
                    f"Unable to find namespace '{namespace}' or deploy token '{token_name}' for '{tool_name}'"
                ) from error

            raise StorageError(
                f"Got unexpected error when trying to delete config for {tool_name}"
            ) from error

    def delete_deploy_token(self, tool_name: str) -> DeployToken:
        token = self.get_deploy_token(tool_name)

        self._delete_deploy_token_crd(tool_name=tool_name)
        self._delete_deploy_token_envvar(tool_name=tool_name)
        return token
