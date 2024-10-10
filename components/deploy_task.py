from functools import lru_cache
from logging import getLogger
from pathlib import Path
from typing import cast

from toolforge_weld.api_client import ToolforgeClient
from toolforge_weld.kubernetes_config import Kubeconfig

from .gen.toolforge_models import JobsJobResponse, JobsNewJob
from .models.api_models import Deployment, RunInfo, ToolConfig
from .settings import get_settings

logger = getLogger(__name__)


@lru_cache()
def load_kubeconfig(namespace: str, server: str) -> Kubeconfig:
    try:
        logger.debug("Trying to load the kubeconfig certs from /etc/components-api")
        kubeconfig = Kubeconfig(
            current_namespace=namespace,
            client_cert_file=Path("/etc/components-api/tls.crt"),
            client_key_file=Path("/etc/components-api/tls.key"),
            ca_file=Path("/etc/components-api/ca.crt"),
            current_server=server,
        )
        logger.debug("Loaded kubeconfig from service account")
    except Exception:
        logger.debug("Trying to load the kubeconfig from common paths")
        kubeconfig = Kubeconfig.load()
        logger.debug("Loaded kubeconfig from common path")
    return kubeconfig


def do_deploy(tool_name: str, tool_config: ToolConfig, deployment: Deployment) -> None:
    for component_name, component_info in tool_config.components.items():
        # TODO: add support to load all the components jobs and then sync the current status
        if component_info.component_type == "continuous":
            deploy_continuous_jobs(
                tool_name=tool_name,
                run_info=component_info.run,
                component_name=component_name,
                image_name=component_info.build.use_prebuilt,
            )


def deploy_continuous_jobs(
    tool_name: str, component_name: str, run_info: RunInfo, image_name: str
) -> None:
    # TODO: support multiple run infos/jobs

    settings = get_settings()
    toolforge_client = ToolforgeClient(
        server=str(settings.toolforge_api_url),
        kubeconfig=load_kubeconfig(
            namespace=settings.namespace, server=str(settings.toolforge_api_url)
        ),
        user_agent="Toolforge components-api",
    )
    # TODO: delete all the other jobs that we don't manage
    logger.debug(
        f"Creating job for component {component_name} with image {image_name} and run_info {run_info}"
    )
    new_job = run_info_to_job(
        component_name=component_name, run_info=run_info, image_name=image_name
    )
    logger.debug(f"Sending job info {new_job}")
    create_response = cast(
        JobsJobResponse,
        toolforge_client.post(
            f"/jobs/v1/tool/{tool_name}/jobs/",
            json=new_job.model_dump(mode="json", exclude_none=True),
        ),
    )
    logger.debug(f"Deployed continuous job {component_name}: {create_response}")


def run_info_to_job(
    component_name: str, run_info: RunInfo, image_name: str
) -> JobsNewJob:
    # TODO: the generator seems to make every parameter mandatory :/, try to fix that somehow
    return JobsNewJob(
        cmd=run_info.command,
        name=component_name,
        imagename=image_name,
        continuous=True,
        cpu=None,
        emails=None,
        filelog=None,
        filelog_stderr=None,
        filelog_stdout=None,
        health_check=None,
        memory=None,
        mount=None,
        port=None,
        replicas=None,
        retry=None,
        schedule=None,
    )
