import datetime
from logging import getLogger

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, APIKeyQuery

from components.settings import Settings

from ..storage.base import Storage
from ..storage.exceptions import NotFoundInStorage
from ..storage.utils import get_storage

TOOL_HEADER = "x-toolforge-tool"
LOGGER = getLogger(name=__name__)

api_key_header = APIKeyHeader(name="x-toolforge-tool", auto_error=False)
token_parameter = APIKeyQuery(name="token", auto_error=False)


def ensure_authenticated(api_key_header: str | None = Security(api_key_header)) -> bool:
    """
    The gateway already checks that the path and the tool match, we only need to check that the tool header is set.
    """
    if not api_key_header:
        raise HTTPException(
            status_code=401, detail=f"The '{TOOL_HEADER}' header is required"
        )
    return True


async def ensure_token_or_auth(
    toolname: str,
    api_key_header: str | None = Security(api_key_header),
    token: str | None = Security(token_parameter),
    storage: Storage = Depends(get_storage),
) -> bool:
    if not api_key_header and not token:
        raise HTTPException(
            status_code=401,
            detail=f"The '{TOOL_HEADER}' header or a token are required",
        )

    if api_key_header:
        return True

    try:
        stored_token = await storage.get_deploy_token(tool_name=toolname)
    except NotFoundInStorage as error:
        raise HTTPException(
            status_code=401,
            detail=f"The token passed '{token}' does not match the tool's token",
        ) from error

    if str(stored_token.token) != token:
        LOGGER.debug(
            f"Got bad token '{token!r}' for tool '{toolname}', stored token is '{stored_token.token!r}'"
        )
        raise HTTPException(
            status_code=401,
            detail=f"The token passed '{token}' does not match the tool's token",
        )

    settings = Settings()
    now = datetime.datetime.now(tz=datetime.UTC)
    expiry_date = stored_token.creation_date + settings.token_lifetime
    if expiry_date < now:
        raise HTTPException(
            status_code=401,
            detail=f"The token passed '{token}' has expired, please create a new one",
        )

    return True
