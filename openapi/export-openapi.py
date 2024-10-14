import argparse
import json
import logging
import os
import subprocess
import sys

import yaml
from uvicorn.importer import import_from_string  # type: ignore

script_dir = os.path.dirname(os.path.abspath(__file__))
default_output_path = os.path.join(script_dir, "openapi.yaml")

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
        if args.out.endswith(".json"):
            json.dump(openapi, f, indent=2)
        else:
            yaml.dump(openapi, f, sort_keys=False)

    logger.info(f"Spec written to {args.out}")
    subprocess.check_call(
        [
            "bash",
            "-c",
            f"[[ $(git diff {args.out}) == '' ]] || {{ echo 'changes to the openapi.yaml detected! please commit them first.'; exit 1; }}",
        ]
    )
