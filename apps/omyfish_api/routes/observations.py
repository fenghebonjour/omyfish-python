from typing import Optional

from fastapi import APIRouter, Depends

from apps.omyfish_api.auth import get_current_user, get_optional_user
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


# Requires auth and always scopes to the caller — an anonymous request used to fall through
# to repo.list()'s unfiltered branch and return every user's coordinates/species/timestamps
# (the same branch /observations/geojson below uses deliberately for its public map feed).
# Matches the family convention: the bare listing endpoint requires auth in
# dotnet/java/python-web too, only the geojson variant is intentionally public
# (BACKLOG.md item B, WEAKNESS_AUDIT.md bonus finding 2).
@router.get("/observations")
def list_observations(
    limit: int = 100,
    repo=Depends(get_obs_repo),
    current_user: TokenData = Depends(get_current_user),
):
    return repo.list(limit, user_id=current_user.user_id)


@router.get("/observations/geojson")
def observations_geojson(
    limit: int = 1000,
    repo=Depends(get_obs_repo),
    gis_service=Depends(get_gis_service),
):
    return gis_service.to_geojson(repo.list(limit))
