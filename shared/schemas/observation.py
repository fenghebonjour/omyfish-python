from pydantic import BaseModel
from typing import Optional


class ObservationCreate(BaseModel):
    species_name: str
    scientific_name: Optional[str] = None
    confidence: float
    latitude: float
    longitude: float
    user_id: Optional[str] = None
    source: str = "manual"
    image_url: Optional[str] = None
