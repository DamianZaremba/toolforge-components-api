import logging
from functools import lru_cache

from pydantic_settings import BaseSettings

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    log_level: str = "info"
    port: int = 8000
    address: str = "127.0.0.1"


@lru_cache()
def get_settings() -> BaseSettings:
    log.info("Loading config settings from the environment...")
    return Settings()
