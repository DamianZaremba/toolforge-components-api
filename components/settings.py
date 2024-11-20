import datetime
import logging
from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    log_level: str = "info"
    port: int = 8000
    address: str = "127.0.0.1"
    storage_type: Literal["mock", "kubernetes"] = "mock"
    toolforge_api_url: AnyHttpUrl = AnyHttpUrl(
        "https://api.svc.tools.eqiad1.wikimedia.cloud"
    )
    verify_toolforge_api_cert: bool = True
    namespace: str = "components-api"
    token_lifetime: datetime.timedelta = datetime.timedelta(days=365)
    max_deployments_retained: int = 25


@lru_cache()
def get_settings() -> Settings:
    log.info("Loading config settings from the environment...")
    return Settings()
