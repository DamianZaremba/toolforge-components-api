import logging

from fastapi import Depends

from ..settings import Settings, get_settings
from .base import Runtime
from .toolforge import ToolforgeRuntime

logger = logging.getLogger(__name__)

# cached loaded storage
runtime: Runtime | None = None


def get_runtime(settings: Settings = Depends(get_settings)) -> Runtime:
    global runtime
    if runtime is None:
        if settings.runtime_type == "toolforge":
            logger.info("Returning toolforge runtime")
            runtime = ToolforgeRuntime()
        else:
            raise ValueError(f"Invalid runtime type: {settings.runtime_type}")

    return runtime
