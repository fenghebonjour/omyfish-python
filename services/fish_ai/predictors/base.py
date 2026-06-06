from abc import ABC, abstractmethod
from PIL import Image


class BaseFishPredictor(ABC):
    @abstractmethod
    def predict(self, image: Image.Image, top_k: int = 3) -> dict:
        ...
