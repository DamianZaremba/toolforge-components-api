import logging

import toml
from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import base, tool
from .api.exceptions import http_exception_handler, validation_exception_handler
from .settings import get_settings

LOGGER = logging.getLogger(__name__)


def get_project_metadata() -> tuple[str, str]:
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
    api_router = APIRouter(prefix="/v1")

    api_router.include_router(base.router)
    api_router.include_router(tool.router, tags=["tool"])

    app.include_router(api_router)

    # Custom exception handlers
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    return app


app = create_app()
