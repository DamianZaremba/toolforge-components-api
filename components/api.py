import logging

from fastapi import APIRouter, FastAPI

from components.settings import get_settings

LOGGER = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
def read_root():
    return {"hello": "world"}


@router.get("/healthz")
def healthz():
    return {"status": "ok"}


def create_app() -> FastAPI:
    settings = get_settings()
    try:
        level = getattr(logging, settings.log_level.upper())
    except AttributeError:
        level = logging.INFO

    logging.basicConfig(level=level)
    LOGGER.debug("Got settings: %r", settings)

    app = FastAPI()
    app.include_router(router)

    return app
