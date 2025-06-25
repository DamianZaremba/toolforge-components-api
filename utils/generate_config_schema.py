#!/usr/bin/env python3
import json
import sys
from copy import deepcopy
from pathlib import Path

import jsonref  # type: ignore
import yaml

TOOL_CONFIG_PATH = ["components", "schemas", "ToolConfig-Input"]
CURDIR = Path(__file__).parent


def main() -> None:
    spec = yaml.safe_load(Path(f"{CURDIR}/../openapi/openapi.yaml").open())
    resolved = jsonref.JsonRef.replace_refs(spec)

    node = resolved
    for key in TOOL_CONFIG_PATH:
        node = node.get(key)
        if node is None:
            print(f"Path {'.'.join(TOOL_CONFIG_PATH)} not found.", file=sys.stderr)
            sys.exit(1)

    # we need to create a standard dict, the one returned by jsonref is not serializable
    print(json.dumps(deepcopy(node), indent=2))


if __name__ == "__main__":
    main()
