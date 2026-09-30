import logging
from copy import deepcopy
from typing import Any, Literal

logger = logging.getLogger(__name__)

V1BETA1 = "v1beta1"
V1BETA2 = "v1beta2"


def infer_component_type(
    run: dict[str, Any],
) -> Literal["scheduled", "continuous"]:

    if "schedule" in run:
        return "scheduled"

    return "continuous"


def upgrade_tool_config_dict(data: dict[str, Any]) -> dict[str, Any]:
    """
    Upgrade a raw v1beta1 tool-config dict toward v1beta2.
    """
    if not isinstance(data, dict):
        return data

    if not isinstance(data.get("components"), dict):
        return data

    config_copy = deepcopy(data)
    config_upgraded = False
    for name, component in config_copy.get("components", {}).items():
        if not isinstance(component, dict):
            continue
        if not isinstance(component.get("run"), dict):
            continue
        inferred_component_type = infer_component_type(component.get("run", {}))
        if component.get("component_type") != inferred_component_type:
            component["component_type"] = inferred_component_type
            config_upgraded = True
            logger.info(
                f"upgraded component {name}: component_type set to {inferred_component_type} for '{name}' component",
            )

    if config_copy.get("config_version") == V1BETA1:
        config_copy["config_version"] = V1BETA2
        config_upgraded = True

    if config_upgraded:
        logger.info("upgraded tool config dict to v1beta2")

    return config_copy


def upgrade_deployment_dict(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return data

    deployment_copy = deepcopy(data)
    tool_config = deployment_copy.get("tool_config")
    if isinstance(tool_config, dict):
        deployment_copy["tool_config"] = upgrade_tool_config_dict(tool_config)
    return deployment_copy
