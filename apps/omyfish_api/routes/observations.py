from typing import Optional

from fastapi import APIRouter, Depends

from apps.omyfish_api.auth import get_optional_user
from apps.omyfish_api.dependencies import get_gis_service, get_obs_repo
from shared.schemas.observation import ObservationCreate
from shared.schemas.user import TokenData

router = APIRouter()


@router.post("/observations")
def create_observation(
    obs: ObservationCreate,
    repo=Depends(get_obs_repo),
    current_user: Optional[TokenData] = Depends(get_optional_user),
):
    if current_user and not obs.user_id:
        obs = obs.model_copy(update={"user_id": current_user.user_id})
    return {"id": repo.create(obs), "status": "created"}


@router.get("/observations")
def list_observations(limit: int = 100, repo=Depends(get_obs_repo)):
    return repo.list(limit)


@router.get("/observations/geojson")
def observations_geojson(
    limit: int = 1000,
    repo=Depends(get_obs_repo),
    gis_service=Depends(get_gis_service),
):
    return gis_service.to_geojson(repo.list(limit))
