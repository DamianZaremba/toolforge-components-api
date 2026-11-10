import re
from typing import Any

import pytest
from pydantic import ValidationError

from components.models.api_models import (
    AnyGitUrl,
    ComponentInfo,
    ContinuousComponentInfo,
    ContinuousRunInfo,
    ScheduledComponentInfo,
    ScheduledRunInfo,
    SourceBuildInfo,
    ToolConfig,
)
from tests.utils import cases

BUILD_JSON = {
    "repository": "https://gitlab-example.wikimedia.org/my-repo.git",
    "ref": "main",
}
BUILD = SourceBuildInfo(repository=AnyGitUrl(BUILD_JSON["repository"]), ref="main")
SKIP_UNTIL_UNKNOWN_FIELDS_ARE_REJECTED = pytest.mark.skip(
    reason="unknown fields are silently dropped instead of rejected"
)


class TestComponentInfo:
    @cases(
        "component_json,expected_model_object",
        [
            "no component_type, command only -> continuous",
            [
                {"run": {"command": "my-command"}},
                ContinuousComponentInfo(
                    build=BUILD, run=ContinuousRunInfo(command="my-command")
                ),
            ],
        ],
        [
            "no component_type, command and schedule -> scheduled",
            [
                {"run": {"command": "my-command", "schedule": "@daily"}},
                ScheduledComponentInfo(
                    build=BUILD,
                    run=ScheduledRunInfo(command="my-command", schedule="@daily"),
                ),
            ],
        ],
        [
            "component_type continuous, command -> continuous",
            [
                {"component_type": "continuous", "run": {"command": "my-command"}},
                ContinuousComponentInfo(
                    build=BUILD, run=ContinuousRunInfo(command="my-command")
                ),
            ],
        ],
        [
            "component_type scheduled, command and schedule -> scheduled",
            [
                {
                    "component_type": "scheduled",
                    "run": {"command": "my-command", "schedule": "@daily"},
                },
                ScheduledComponentInfo(
                    build=BUILD,
                    run=ScheduledRunInfo(command="my-command", schedule="@daily"),
                ),
            ],
        ],
    )
    def test_component_parsing_succeeds(
        self,
        component_json: dict[str, Any],
        expected_model_object: ComponentInfo,
    ):
        tool_config_json = {
            "components": {"my-component": {"build": BUILD_JSON, **component_json}}
        }

        tool_config = ToolConfig.model_validate(tool_config_json)

        assert tool_config.components["my-component"] == expected_model_object

    @cases(
        "component_json,expected_error",
        [
            "no component_type, command, schedule and port -> error: schedule not allowed with port",
            pytest.param(
                {
                    "run": {
                        "command": "my-command",
                        "schedule": "@daily",
                        "port": 8000,
                    }
                },
                "ContinuousComponentInfo.run.schedule",
                marks=SKIP_UNTIL_UNKNOWN_FIELDS_ARE_REJECTED,
            ),
        ],
        [
            "no component_type, command, schedule, timeout and port -> error: port not allowed with schedule",
            pytest.param(
                {
                    "run": {
                        "command": "my-command",
                        "schedule": "@daily",
                        "timeout": 60,
                        "port": 8000,
                    }
                },
                "ScheduledComponentInfo.run.port",
                marks=SKIP_UNTIL_UNKNOWN_FIELDS_ARE_REJECTED,
            ),
        ],
        [
            "no component_type, no run fields -> error: command required",
            [{"run": {}}, "ContinuousComponentInfo.run.command"],
        ],
        [
            "no component_type, no run -> error: run required",
            [{}, "ContinuousComponentInfo.run"],
        ],
        [
            "component_type continuous, command and schedule -> error: schedule not allowed",
            pytest.param(
                {
                    "component_type": "continuous",
                    "run": {"command": "my-command", "schedule": "@daily"},
                },
                "ContinuousComponentInfo.run.schedule",
                marks=SKIP_UNTIL_UNKNOWN_FIELDS_ARE_REJECTED,
            ),
        ],
        [
            "component_type scheduled, command, schedule and port -> error: port not allowed",
            pytest.param(
                {
                    "component_type": "scheduled",
                    "run": {
                        "command": "my-command",
                        "schedule": "@daily",
                        "port": 8000,
                    },
                },
                "ScheduledComponentInfo.run.port",
                marks=SKIP_UNTIL_UNKNOWN_FIELDS_ARE_REJECTED,
            ),
        ],
        [
            "component_type scheduled, command without schedule -> error: schedule required",
            [
                {"component_type": "scheduled", "run": {"command": "my-command"}},
                "ScheduledComponentInfo.run.schedule",
            ],
        ],
        [
            "unknown component_type -> error: component_type not allowed",
            [
                {"component_type": "webservce", "run": {"command": "my-command"}},
                "ContinuousComponentInfo.component_type",
            ],
        ],
        [
            "empty component_type -> error: component_type not allowed",
            [
                {"component_type": None, "run": {"command": "my-command"}},
                "ContinuousComponentInfo.component_type",
            ],
        ],
    )
    def test_component_parsing_fails(
        self, component_json: dict[str, Any], expected_error: str
    ):
        tool_config_json = {
            "components": {"my-component": {"build": BUILD_JSON, **component_json}}
        }

        with pytest.raises(ValidationError, match=f"{re.escape(expected_error)}\n"):
            ToolConfig.model_validate(tool_config_json)
