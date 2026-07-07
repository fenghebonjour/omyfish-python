"""
Zero-shot "is this a fish?" gate using CLIP.
Runs before the closed-set EfficientNet classifier so non-fish images
(cats, dogs, people, ...) are rejected instead of being forced into a fish class.
"""

import torch
import torch.nn.functional as F
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

MODEL_ID = "openai/clip-vit-base-patch32"
FISH_THRESHOLD = 0.50

FISH_PROMPTS = [
    "a photo of a fish",
    "a fish underwater",
    "a closeup of a fish",
    "a person holding a caught fish",
]

NON_FISH_PROMPTS = [
    "a photo of a cat",
    "a photo of a dog",
    "a photo of a person",
    "a photo of a bird",
    "a photo of an insect",
    "a photo of food on a plate",
    "a photo of a landscape",
    "a photo of a building",
    "a photo of an everyday object",
]


class FishGate:
    def __init__(self):
        self.model = CLIPModel.from_pretrained(MODEL_ID)
        self.processor = CLIPProcessor.from_pretrained(MODEL_ID)
        self.model.eval()
        self.text_embeddings = self._build_text_embeddings()
        self.num_fish = len(FISH_PROMPTS)

    @torch.no_grad()
    def _build_text_embeddings(self) -> torch.Tensor:
        prompts = FISH_PROMPTS + NON_FISH_PROMPTS
        inputs = self.processor(text=prompts, return_tensors="pt", padding=True, truncation=True)

        text_out = self.model.text_model(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
        )
        text_feats = self.model.text_projection(text_out.pooler_output)
        return F.normalize(text_feats, dim=-1)

    @torch.no_grad()
    def is_fish(self, image: Image.Image) -> tuple[bool, float]:
        inputs = self.processor(images=image.convert("RGB"), return_tensors="pt")

        image_out = self.model.vision_model(pixel_values=inputs["pixel_values"])
        image_feats = self.model.visual_projection(image_out.pooler_output)
        image_feats = F.normalize(image_feats, dim=-1)

        logits = 100.0 * (image_feats @ self.text_embeddings.T)
        probs = logits.softmax(dim=-1)[0]

        fish_prob = probs[: self.num_fish].sum().item()
        return fish_prob >= FISH_THRESHOLD, round(fish_prob, 4)
