import logging

import toml
from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api import base_router, tool_router
from .api.exceptions import (
    http_exception_handler,
    validation_exception_handler,
)
from .metrics import get_metrics_app
from .settings import Settings, get_settings

LOGGER = logging.getLogger(__name__)


def get_project_metadata() -> tuple[str, str]:
    with open("pyproject.toml", "r") as pyproject_file:
        pyproject_data = toml.load(pyproject_file)
        metadata = pyproject_data["tool"]["poetry"]
        return metadata["description"], metadata["version"]


title, version = get_project_metadata()


def use_route_names_as_operation_ids(app: FastAPI) -> None:
    """
    Simplify operation IDs so that generated API clients have simpler function
    names.

    Should be called only after all routes have been added.
    """
    for route in app.routes:
        if isinstance(route, APIRoute):
            route.operation_id = route.name


def create_app(settings: Settings | None = None) -> FastAPI:
    if not settings:
        settings = get_settings()
    try:
        level = getattr(logging, settings.log_level.upper())
    except AttributeError:
        level = logging.INFO

    logging.basicConfig(level=level)
    # this is needed mostly for the tests, as you can't change the loglevel with basicConfig once it has
    # been changed once
    logging.root.setLevel(level=level)
    LOGGER.debug("Got settings: %r", settings)

    app = FastAPI(
        title=title,
        servers=[
            {
                "url": "http://127.0.0.1:8000",
                "description": "Local direct development server.",
            },
            {
                "url": "https://127.0.0.1:3000/components",
                "description": "Lima-kilo development server.",
            },
            {
                "url": "https://api.svc.tools.eqiad1.wikimedia.cloud:30003/components",
                "description": "Toolforge internal API gateway endpoint.",
            },
            {
                "url": "https://api.svc.toolsbeta.eqiad1.wikimedia.cloud:30003/components",
                "description": "Toolforge beta internal API gateway endpoint.",
            },
            {
                "url": "https://api.svc.toolforge.org/components",
                "description": "Toolforge external API gateway endpoint.",
            },
            {
                "url": "https://api.svc.beta.toolforge.org/components",
                "description": "Toolforge beta external API gateway endpoint.",
            },
        ],
        version=version,
    )

    # Initialize metrics
    metrics_app = get_metrics_app()
    metrics_app(app)

    # Top-level API router
    api_router = APIRouter(prefix="/v1")

    api_router.include_router(base_router.router)
    api_router.include_router(tool_router.header_auth_router, tags=["tool"])
    api_router.include_router(tool_router.token_auth_router, tags=["tool"])

    app.include_router(api_router)

    # Custom exception handlers
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    use_route_names_as_operation_ids(app)

    return app


app = create_app()
