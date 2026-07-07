from pydantic import BaseModel
from typing import Optional, List


class PredictionResult(BaseModel):
    species: str
    confidence: float
    metadata: Optional[dict] = None


class PredictionResponse(BaseModel):
    predictions: List[PredictionResult]
    uncertain: bool
    message: Optional[str] = None
    is_fish: bool = True
