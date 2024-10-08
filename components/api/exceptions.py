from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..models.api_models import ApiResponse, ResponseMessages


def _format_validation_error(error: dict[str, Any]) -> str:
    error_type = error.get("type", "")
    if error_type == "json_invalid":
        loc = error.get("loc", [])
        if len(loc) > 1:
            position = loc[1]
        else:
            position = "unknown position"
        ctx = error.get("ctx", {})
        ctx_error = ctx.get("error", "Unknown JSON error")
        return f"Invalid JSON at position {position}: {ctx_error}"

    loc = " -> ".join(str(item) for item in error.get("loc", [])[1:])
    msg = error.get("msg", "")
    input_value = error.get("input")

    error_msg = f"Validation error at {loc}: {msg}"
    if input_value is not None:
        error_msg += f". Received value: '{input_value}'"

    return error_msg


async def http_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    # Needed because of https://github.com/encode/starlette/discussions/2416
    if not isinstance(exc, StarletteHTTPException):
        raise Exception("Unable to handle {exc}")
    api_response: ApiResponse[None] = ApiResponse(
        data=None,
        messages=ResponseMessages(error=[str(exc.detail)], info=[], warning=[]),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=api_response.model_dump(exclude_none=True),
    )


async def validation_exception_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    # Needed because of https://github.com/encode/starlette/discussions/2416
    if not isinstance(exc, RequestValidationError):
        raise Exception("Unable to handle {exc}")
    formatted_errors = [_format_validation_error(error) for error in exc.errors()]
    api_response: ApiResponse[None] = ApiResponse(
        data=None,
        messages=ResponseMessages(error=formatted_errors, info=[], warning=[]),
    )
    return JSONResponse(
        status_code=422,
        content=api_response.model_dump(exclude_none=True),
    )
