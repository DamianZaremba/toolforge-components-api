import logging

import toml
from fastapi import FastAPI

from components.api import base, tool
from components.settings import get_settings

LOGGER = logging.getLogger(__name__)


API_PREFIX = "/v1"


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
    app.include_router(base.router, prefix=API_PREFIX)
    app.include_router(tool.router, prefix=API_PREFIX, tags=["tool"])

    return app
