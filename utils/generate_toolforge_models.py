#!/usr/bin/env python3
import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

TOOLFORGE_OPENAPI_URL = "https://api.svc.toolforge.org/openapi.json"
CURDIR = Path(__file__).parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target-python-version",
        help="python version to target, instead of the one from pyproject.toml",
    )
    args = parser.parse_args()

    python_version = args.target_python_version
    if python_version is None:
        with Path(f"{CURDIR}/../pyproject.toml").open("rb") as pyproject_fd:
            pyproject = tomllib.load(pyproject_fd)
        # python version the repo officially supports
        python_constraint = pyproject["tool"]["poetry"]["dependencies"]["python"]
        python_version = re.findall(r"\d+\.\d+", python_constraint)[0]

    subprocess.run(
        [
            sys.executable,
            "-m",
            "datamodel_code_generator",
            "--url",
            TOOLFORGE_OPENAPI_URL,
            "--output",
            "components/gen/toolforge_models.py",
            "--output-model-type",
            "pydantic_v2.BaseModel",
            "--use-annotated",
            "--target-python-version",
            python_version,
            "--formatters",
            "ruff-check",
            "ruff-format",
        ],
        cwd=CURDIR.parent,
        check=True,
    )


if __name__ == "__main__":
    main()
