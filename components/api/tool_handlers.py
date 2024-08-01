from fastapi import HTTPException

from components.models.pydantic import (
    ApiResponse,
    Config,
    ConfigResponse,
    Deployment,
    DeploymentResponse,
)

# Mock data
MOCK_CONFIGS = {"tf-test": {"config": "tf-test_config"}}

MOCK_DEPLOYMENTS = {
    "12345": Deployment(deploy_id="12345", toolname="tf-test", status="in_progress")
}

MOCK_TOOL_NAME = "tf-test"


def get_tool_config(toolname: str) -> ConfigResponse:
    """Retrieve the configuration for a specific tool."""
    if toolname in MOCK_CONFIGS:
        return ConfigResponse(data=MOCK_CONFIGS[toolname], messages={})
    raise HTTPException(status_code=404, detail="Configuration not found")


def update_tool_config(toolname: str, config: Config) -> ApiResponse:
    """Update the configuration for a specific tool."""
    return ApiResponse(
        data={"message": f"Configuration for {toolname} updated successfully"},
        messages={},
    )


def create_deployment(toolname: str) -> DeploymentResponse:
    """Create a new deployment for a specific tool."""
    new_deploy_id = str(len(MOCK_DEPLOYMENTS) + 1).zfill(5)
    new_deployment = Deployment(
        deploy_id=new_deploy_id, toolname=toolname, status="started"
    )
    MOCK_DEPLOYMENTS[new_deploy_id] = new_deployment
    return DeploymentResponse(data=new_deployment, messages={})


def get_deployment(toolname: str, deploy_id: str) -> DeploymentResponse:
    """Retrieve a specific deployment for a tool."""
    if deploy_id in MOCK_DEPLOYMENTS:
        deployment = MOCK_DEPLOYMENTS[deploy_id]
        if deployment.toolname == toolname:
            return DeploymentResponse(data=deployment, messages={})
    raise HTTPException(status_code=404, detail="Deployment not found")
