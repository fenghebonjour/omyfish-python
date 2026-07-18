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
        self._gate = None
        self._gate_failed = False

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

    def _fish_gate(self):
        if self._gate is None and not self._gate_failed:
            try:
                from services.fish_ai.predictors.fish_gate import FishGate
                self._gate = FishGate()
            except Exception:
                self._gate_failed = True
        return self._gate

    def predict(self, image: Image.Image, top_k: int = 3) -> dict:
        gate = self._fish_gate()
        if gate is not None and not gate.is_fish(image)[0]:
            return {
                "predictions": [],
                "uncertain": True,
                "is_fish": False,
                "message": "That doesn't look like a fish — try a clear photo of a fish.",
            }
        result = self._predictor.predict(image, top_k=top_k)
        result["is_fish"] = True
        if self._gate_failed:
            result["gate_unavailable"] = True
        return result
