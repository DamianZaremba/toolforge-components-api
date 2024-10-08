from fastapi import APIRouter

from components.models.api_models import HealthState, HealthzResponse

router = APIRouter()


@router.get("/healthz")
def healthz() -> HealthzResponse:
    # TODO: do some actual checks
    return HealthzResponse(data=HealthState(status="OK"))
