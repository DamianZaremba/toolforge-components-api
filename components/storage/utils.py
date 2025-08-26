import logging

from fastapi import Depends

from ..settings import Settings, get_settings
from .base import Storage
from .kubernetes import KubernetesStorage
from .mock import MockStorage

logger = logging.getLogger(__name__)

# cached loaded storage
storage: Storage | None = None


def get_storage(
    settings: Settings = Depends(get_settings), rebuild_storage: bool = False
) -> Storage:
    global storage
    if storage is None or rebuild_storage:
        if settings.storage_type == "mock":
            logger.info("Returning mock storage")
            storage = MockStorage()

        elif settings.storage_type == "kubernetes":
            logger.info("Returning kubernetes storage")
            storage = KubernetesStorage()
        else:
            raise ValueError(f"Invalid storage type: {settings.storage_type}")

    return storage
