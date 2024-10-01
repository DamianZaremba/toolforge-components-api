import logging

import toml
from fastapi import APIRouter, FastAPI

from components.api import base, tool
from components.settings import get_settings

LOGGER = logging.getLogger(__name__)


def get_project_metadata():
    with open("pyproject.toml", "r") as pyproject_file:
        pyproject_data = toml.load(pyproject_file)
        metadata = pyproject_data["tool"]["poetry"]
        return metadata["description"], metadata["version"]


title, version = get_project_metadata()


def create_app() -> FastAPI:
    settings = get_settings()
    try:
        level = getattr(logging, settings.log_level.upper())
    except AttributeError:
        level = logging.INFO

    logging.basicConfig(level=level)
    LOGGER.debug("Got settings: %r", settings)

    app = FastAPI(title=title, version=version)

    # Top-level API router
    api_router = APIRouter(prefix=settings.api_prefix)

    api_router.include_router(base.router)
    api_router.include_router(tool.router, tags=["tool"])

    app.include_router(api_router)

    return app


app = create_app()
