import logging
from functools import lru_cache
from pathlib import Path

from toolforge_weld.api_client import ToolforgeClient
from toolforge_weld.kubernetes_config import Kubeconfig

from .settings import get_settings

logger = logging.getLogger(__name__)


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
        logger.debug("Loaded the kubeconfig certs from /etc/components-api")
    except Exception:
        logger.debug("Trying to load the kubeconfig from common paths")
        kubeconfig = Kubeconfig.load()
        logger.debug("Loaded kubeconfig from common path")
    return kubeconfig


def get_toolforge_client() -> ToolforgeClient:
    settings = get_settings()
    kubeconfig = load_kubeconfig(
        namespace=settings.namespace, server=str(settings.toolforge_api_url)
    )
    return ToolforgeClient(
        server=str(settings.toolforge_api_url),
        kubeconfig=kubeconfig,
        user_agent="Toolforge components-api",
    )
