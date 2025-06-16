import datetime
import logging
from typing import Literal

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    log_level: str = "info"
    port: int = 8000
    address: str = "127.0.0.1"
    storage_type: Literal["mock", "kubernetes"] = "mock"
    runtime_type: Literal["toolforge"] = "toolforge"
    toolforge_api_url: AnyHttpUrl = AnyHttpUrl(
        "https://api.svc.tools.eqiad1.wikimedia.cloud"
    )
    verify_toolforge_api_cert: bool = True
    namespace: str = "components-api"
    token_lifetime: datetime.timedelta = datetime.timedelta(days=365)
    max_deployments_retained: int = 25
    build_timeout_seconds: int = 60 * 30
    # we might be able to increase this when we allow deploying specific components
    # until then, any deployment will potentially conflict with any other
    max_parallel_deployments: int = 1
    deployment_timeout: datetime.timedelta = datetime.timedelta(hours=1)


def get_settings() -> Settings:
    global settings
    if not settings:
        log.info("Loading config settings from the environment...")
        settings = Settings()

    return settings


settings: Settings | None = None
