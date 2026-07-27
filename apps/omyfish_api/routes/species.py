import io
from typing import Optional

import requests
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from PIL import Image

from apps.omyfish_api.dependencies import get_ai_service, get_gis_service, get_obs_repo
from shared.config import settings
from shared.schemas.observation import ObservationCreate

router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
REGS_TIMEOUT_SECONDS = 5


def _fetch_regs(lat: float, lon: float, species: str) -> dict:
    """Best-effort call to the shared omyfish-ai regs_advisor endpoints.
    Additive enrichment only — any failure (service down, no data for this
    species/location) must not break the identify_fish response."""
    regs: dict = {}
    try:
        resp = requests.get(
            f"{settings.bite_service_url}/regs/limits",
            params={"lat": lat, "lon": lon, "species": species},
            timeout=REGS_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            regs["legal_limit"] = resp.json()
    except requests.RequestException:
        pass
    try:
        resp = requests.get(
            f"{settings.bite_service_url}/regs/consumption",
            params={"lat": lat, "lon": lon, "species": species},
            timeout=REGS_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            regs["consumption_advice"] = resp.json()
    except requests.RequestException:
        pass
    return regs


def _open_image(data: bytes) -> Image.Image:
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Image too large (max 10 MB).")
    try:
        return Image.open(io.BytesIO(data))
    except Exception:
        raise HTTPException(400, "File is not a valid image.")


@router.post("/predict")
async def predict(
    file: UploadFile = File(...),
    top_k: int = 3,
    ai_service=Depends(get_ai_service),
):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(400, "File must be an image.")
    image = _open_image(await file.read())
    return ai_service.predict(image, top_k=top_k)


@router.post("/identify-fish")
async def identify_fish(
    file: UploadFile = File(...),
    top_k: int = Form(3),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    save: bool = Form(False),
    user_id: Optional[str] = Form(None),
    ai_service=Depends(get_ai_service),
    gis_service=Depends(get_gis_service),
    repo=Depends(get_obs_repo),
):
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(400, "File must be an image.")

    image = _open_image(await file.read())
    result = ai_service.predict(image, top_k=top_k)

    coords = None
    if latitude is not None and longitude is not None:
        coords = (latitude, longitude)
        result["location_source"] = "manual"
    else:
        gps = gis_service.extract_gps(image)
        if gps:
            coords = gps
            result["location_source"] = "exif"

    if coords:
        result["latitude"], result["longitude"] = coords
        if result["predictions"]:
            top = result["predictions"][0]
            meta = top.get("metadata") or {}
            species_query = meta.get("species") or top["species"].replace("_", " ")
            result.update(_fetch_regs(coords[0], coords[1], species_query))

    if save and coords and result["predictions"]:
        top = result["predictions"][0]
        meta = top.get("metadata") or {}
        obs = ObservationCreate(
            species_name=top["species"],
            scientific_name=meta.get("scientific_name"),
            confidence=top["confidence"],
            latitude=coords[0],
            longitude=coords[1],
            user_id=user_id,
            source="upload",
        )
        result["observation_id"] = repo.create(obs)

    return result
