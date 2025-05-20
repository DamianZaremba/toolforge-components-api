from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter

from components.models.api_models import (
    HealthState,
    HealthzResponse,
    OpenAPISpecResponse,
)

CURDIR = Path(__file__).parent.absolute()
OPENAPI_YAML_PATH = f"{CURDIR.parent}/openapi/openapi.yaml"

router = APIRouter()


@router.get("/healthz")
def healthz() -> HealthzResponse:
    # TODO: do some actual checks
    return HealthzResponse(data=HealthState(status="OK"))


@router.get("/openapi.json")
def openapi() -> OpenAPISpecResponse:
    with open(OPENAPI_YAML_PATH, "r") as yaml_file:
        openapi_definition: dict[str, Any] = yaml.safe_load(yaml_file)

    return OpenAPISpecResponse(data=openapi_definition)
