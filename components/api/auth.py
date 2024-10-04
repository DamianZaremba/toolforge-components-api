from fastapi import Request

from .exceptions import ToolAuthError

TOOL_HEADER = "x-toolforge-tool"


def ensure_authenticated(request: Request) -> str:
    """
    The gateway already checks that the path and the tool match, we only need to check that the tool header is set.
    """
    tool = request.headers.get(TOOL_HEADER)
    if not tool:
        raise ToolAuthError(message=f"missing '{TOOL_HEADER}' header")
    return tool
