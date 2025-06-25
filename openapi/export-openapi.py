import argparse
import json
import logging
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import jsonref  # type: ignore
import yaml
from uvicorn.importer import import_from_string  # type: ignore

script_dir = os.path.dirname(os.path.abspath(__file__))
default_output_path = Path(script_dir) / "openapi.yaml"
default_config_output_path = Path(script_dir) / "tool-config-schema.json"
tool_config_path = ["components", "schemas", "ToolConfig-Input"]

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

parser = argparse.ArgumentParser(prog="extract-openapi.py")
parser.add_argument(
    "app",
    help='App import string. E.g., "components.main:create_app"',
    default="main:app",
)
parser.add_argument("--app-dir", help="Directory containing the app", default=None)
parser.add_argument(
    "--out", help="Output file ending in .json or .yaml", default=default_output_path
)
parser.add_argument(
    "--tool-config-out",
    help="Output file ending in .json for the tool config schema",
    default=default_config_output_path,
)


def get_tool_config() -> dict[str, Any]:
    spec = yaml.safe_load(Path(f"{script_dir}/../openapi/openapi.yaml").open())
    resolved = jsonref.JsonRef.replace_refs(spec)

    node = resolved
    for key in tool_config_path:
        node = node.get(key)
        if node is None:
            print(f"Path {'.'.join(tool_config_path)} not found.", file=sys.stderr)
            sys.exit(1)

    # we need to create a standard dict, the one returned by jsonref is not serializable
    return deepcopy(node)


if __name__ == "__main__":
    args = parser.parse_args()

    if args.app_dir is not None:
        logger.info(f"Adding {args.app_dir} to sys.path")
        sys.path.insert(0, args.app_dir)

    logger.info(f"Importing app from {args.app}")
    imported = import_from_string(args.app)

    # If the imported object is callable (a factory), call it to get the app
    if callable(imported):
        app = imported()
    else:
        app = imported

    openapi = app.openapi()
    version = openapi.get("openapi", "unknown version")

    logger.info(f"Writing OpenAPI spec v{version}")
    with open(args.out, "w") as f:
        if str(args.out).endswith(".json"):
            json.dump(openapi, f, indent=2)
        else:
            yaml.dump(openapi, f, sort_keys=False)

    with open(args.tool_config_out, "w") as f:
        json.dump(get_tool_config(), f, indent=2)
        # for the fix-end-of-line check
        f.write("\n")

    logger.info(f"Spec written to {args.out}")
    subprocess.check_call(
        [
            "bash",
            "-c",
            f"[[ $(git diff {args.out}) == '' ]] || {{ echo 'changes to the openapi.yaml or tool config detected! please commit them first.'; exit 1; }}",
        ]
    )
