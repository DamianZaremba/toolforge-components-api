from collections.abc import Callable
from logging import getLogger

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

logger = getLogger(__name__)


def get_metrics_app() -> Callable[[FastAPI], None]:
    instrumentator = Instrumentator()

    def instrument_app(app: FastAPI) -> None:
        logger.info("Initializing Prometheus metrics")
        instrumentator.instrument(app).expose(app)

    return instrument_app
