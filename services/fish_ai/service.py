from pathlib import Path
from PIL import Image

from services.fish_ai.predictors.base import BaseFishPredictor


class FishAIService:
    """
    Unified AI inference interface.
    Delegates to the trained EfficientNet model if a checkpoint exists,
    falls back to CLIP zero-shot otherwise.
    """

    def __init__(self, predictor: BaseFishPredictor, mode: str):
        self._predictor = predictor
        self.mode = mode  # "trained" | "clip"

    @classmethod
    def build(
        cls,
        checkpoint_path: str = "checkpoints/best.pt",
        metadata_path: str = "data/metadata/fish_info.json",
    ) -> "FishAIService":
        if Path(checkpoint_path).exists():
            from services.fish_ai.predictors.efficientnet import FishPredictor
            return cls(FishPredictor(checkpoint_path, metadata_path), "trained")
        from services.fish_ai.predictors.clip import CLIPFishPredictor
        return cls(CLIPFishPredictor(metadata_path), "clip")

    def predict(self, image: Image.Image, top_k: int = 3) -> dict:
        return self._predictor.predict(image, top_k=top_k)
