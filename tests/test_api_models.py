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
    WebServiceComponentInfo,
    WebServiceRunInfo,
)
from tests.utils import cases

BUILD_JSON = {
    "repository": "https://gitlab-example.wikimedia.org/my-repo.git",
    "ref": "main",
}
BUILD = SourceBuildInfo(repository=AnyGitUrl(BUILD_JSON["repository"]), ref="main")


class TestComponentInfo:
    @cases(
        "component_json,expected_model_object,expected_error",
        [
            "no component_type, command only -> continuous",
            [
                {"run": {"command": "my-command"}},
                ContinuousComponentInfo(
                    build=BUILD, run=ContinuousRunInfo(command="my-command")
                ),
                None,
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
                None,
            ],
        ],
        [
            "no component_type, command, schedule and port -> continuous",
            [
                {
                    "run": {
                        "command": "my-command",
                        "schedule": "@daily",
                        "port": 8000,
                    }
                },
                ContinuousComponentInfo(
                    build=BUILD, run=ContinuousRunInfo(command="my-command", port=8000)
                ),
                None,
            ],
        ],
        [
            "no component_type, command, schedule, timeout and port -> scheduled",
            [
                {
                    "run": {
                        "command": "my-command",
                        "schedule": "@daily",
                        "timeout": 60,
                        "port": 8000,
                    }
                },
                ScheduledComponentInfo(
                    build=BUILD,
                    run=ScheduledRunInfo(
                        command="my-command", schedule="@daily", timeout=60
                    ),
                ),
                None,
            ],
        ],
        [
            "no component_type, no run fields -> error: webservice needs component_type",
            [{"run": {}}, None, "WebServiceComponentInfo.component_type"],
        ],
        [
            "no component_type, no run -> error: run required",
            [{}, None, "ContinuousComponentInfo.run"],
        ],
        [
            "component_type continuous, command and schedule -> continuous",
            [
                {
                    "component_type": "continuous",
                    "run": {"command": "my-command", "schedule": "@daily"},
                },
                ContinuousComponentInfo(
                    build=BUILD, run=ContinuousRunInfo(command="my-command")
                ),
                None,
            ],
        ],
        [
            "component_type scheduled, command, schedule and port -> scheduled",
            [
                {
                    "component_type": "scheduled",
                    "run": {
                        "command": "my-command",
                        "schedule": "@daily",
                        "port": 8000,
                    },
                },
                ScheduledComponentInfo(
                    build=BUILD,
                    run=ScheduledRunInfo(command="my-command", schedule="@daily"),
                ),
                None,
            ],
        ],
        [
            "component_type scheduled, command without schedule -> error: schedule required",
            [
                {"component_type": "scheduled", "run": {"command": "my-command"}},
                None,
                "ScheduledComponentInfo.run.schedule",
            ],
        ],
        [
            "component_type webservice, no run fields -> webservice",
            [
                {"component_type": "webservice", "run": {}},
                WebServiceComponentInfo(
                    component_type="webservice", build=BUILD, run=WebServiceRunInfo()
                ),
                None,
            ],
        ],
        [
            "component_type webservice, command -> webservice with command",
            [
                {"component_type": "webservice", "run": {"command": "my-command"}},
                WebServiceComponentInfo(
                    component_type="webservice",
                    build=BUILD,
                    run=WebServiceRunInfo(command="my-command"),
                ),
                None,
            ],
        ],
        [
            "component_type webservice, filelog -> webservice",
            [
                {"component_type": "webservice", "run": {"filelog": True}},
                WebServiceComponentInfo(
                    component_type="webservice", build=BUILD, run=WebServiceRunInfo()
                ),
                None,
            ],
        ],
        [
            "component_type webservice, no run -> webservice",
            [
                {"component_type": "webservice"},
                WebServiceComponentInfo(
                    component_type="webservice", build=BUILD, run=WebServiceRunInfo()
                ),
                None,
            ],
        ],
        [
            "component_type webservice, run set to null -> error: run must be a dictionary",
            [
                {"component_type": "webservice", "run": None},
                None,
                "WebServiceComponentInfo.run",
            ],
        ],
        [
            "unknown component_type -> error: component_type not allowed",
            [
                {"component_type": "webservce", "run": {"command": "my-command"}},
                None,
                "ContinuousComponentInfo.component_type",
            ],
        ],
        [
            "empty component_type -> error: component_type not allowed",
            [
                {"component_type": None, "run": {"command": "my-command"}},
                None,
                "ContinuousComponentInfo.component_type",
            ],
        ],
    )
    def test_component_parsing(
        self,
        component_json: dict[str, Any],
        expected_model_object: ComponentInfo | None,
        expected_error: str | None,
    ):
        tool_config_json = {
            "components": {"my-component": {"build": BUILD_JSON, **component_json}}
        }

        if expected_error:
            with pytest.raises(ValidationError, match=f"{re.escape(expected_error)}\n"):
                ToolConfig.model_validate(tool_config_json)
        else:
            tool_config = ToolConfig.model_validate(tool_config_json)
            assert tool_config.components["my-component"] == expected_model_object
