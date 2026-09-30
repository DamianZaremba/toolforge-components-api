from copy import deepcopy

from components.models import migration
from tests.utils import cases

BUILD = {
    "repository": "https://gitlab-example.wikimedia.org/my-repo.git",
    "ref": "main",
}
WITHOUT_COMPONENT_TYPE = {"build": BUILD, "run": {"command": "my-command"}}
WITH_COMPONENT_TYPE = {
    "component_type": "continuous",
    **WITHOUT_COMPONENT_TYPE,
}


def _config(component, *, version: str | None = "v1beta1"):
    return {"config_version": version, "components": {"my-component": component}}


@cases(
    "input_config,expected_output_config",
    [
        "v1beta1 is upgraded to v1beta2 and nothing else changes",
        [
            _config(WITH_COMPONENT_TYPE),
            _config(WITH_COMPONENT_TYPE, version="v1beta2"),
        ],
    ],
    [
        "v1beta1 is upgraded to v1beta2 and the missing component_type is inferred as continuous",
        [
            _config(WITHOUT_COMPONENT_TYPE),
            _config(WITH_COMPONENT_TYPE, version="v1beta2"),
        ],
    ],
    [
        "v1beta1 is upgraded to v1beta2 and the component with a scheduled run is inferred as scheduled",
        [
            _config(
                {
                    **WITHOUT_COMPONENT_TYPE,
                    "run": {"command": "my-command", "schedule": "@daily"},
                }
            ),
            _config(
                {
                    **WITHOUT_COMPONENT_TYPE,
                    "component_type": "scheduled",
                    "run": {"command": "my-command", "schedule": "@daily"},
                },
                version="v1beta2",
            ),
        ],
    ],
    [
        "v1beta1 is upgraded to v1beta2 and a wrong component_type is corrected to match the run",
        [
            _config({**WITHOUT_COMPONENT_TYPE, "component_type": "scheduled"}),
            _config(WITH_COMPONENT_TYPE, version="v1beta2"),
        ],
    ],
    [
        "a v1beta2 config is left alone",
        [
            _config(WITH_COMPONENT_TYPE, version="v1beta2"),
            _config(WITH_COMPONENT_TYPE, version="v1beta2"),
        ],
    ],
)
def test_upgrade_applies_only_the_needed_changes(input_config, expected_output_config):
    snapshot = deepcopy(input_config)
    upgraded = migration.upgrade_tool_config_dict(input_config)
    assert upgraded == expected_output_config
    assert upgraded is not input_config
    assert input_config == snapshot
