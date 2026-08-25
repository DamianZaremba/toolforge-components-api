import logging
from typing import Annotated

from fastapi import Depends

from ..settings import Settings, get_settings
from .base import Storage
from .kubernetes import KubernetesStorage
from .mock import MockStorage

logger = logging.getLogger(__name__)

# cached loaded storage
storage: Storage | None = None


def get_storage(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Storage:
    return inner_get_storage(settings=settings)


def inner_get_storage(
    settings: Settings,
    rebuild_storage: bool = False,
) -> Storage:
    """To avoid rebuild_storage from leaking to the openapi spec and interface."""
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
