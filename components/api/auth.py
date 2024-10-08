from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

TOOL_HEADER = "x-toolforge-tool"

api_key_header = APIKeyHeader(name="x-toolforge-tool", auto_error=False)


def ensure_authenticated(api_key_header: str = Security(api_key_header)) -> bool:
    """
    The gateway already checks that the path and the tool match, we only need to check that the tool header is set.
    """
    if not api_key_header:
        raise HTTPException(
            status_code=401, detail=f"The '{TOOL_HEADER}' header is required"
        )
    return True
