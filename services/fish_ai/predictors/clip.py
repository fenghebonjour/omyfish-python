"""
Zero-shot fish identifier using CLIP with prompt ensembling.

Instead of one prompt per species, we encode multiple templates and
average the text embeddings. This is OpenAI's recommended technique
for improving zero-shot CLIP accuracy without any training.
"""

import json
from pathlib import Path

import torch
import torch.nn.functional as F
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from services.fish_ai.predictors.base import BaseFishPredictor

UNCERTAIN_THRESHOLD = 0.08
MODEL_ID = "openai/clip-vit-base-patch32"

PROMPT_TEMPLATES = [
    "a photo of a {}",
    "a photograph of a {}",
    "a {} fish",
    "a {} swimming in water",
    "a closeup of a {} fish",
    "a {} caught while fishing",
    "a picture of a {} fish in the wild",
    "a {} fish underwater",
]


def _normalize(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


class CLIPFishPredictor(BaseFishPredictor):
    def __init__(self, metadata_path: str = "data/metadata/fish_info.json"):
        self.model = CLIPModel.from_pretrained(MODEL_ID)
        self.processor = CLIPProcessor.from_pretrained(MODEL_ID)
        self.model.eval()

        fish_list = json.loads(Path(metadata_path).read_text())
        self.metadata = {_normalize(f["species"]): f for f in fish_list}
        self.species = [f["species"] for f in fish_list]

        self.text_embeddings = self._build_text_embeddings()

    @torch.no_grad()
    def _build_text_embeddings(self) -> torch.Tensor:
        """
        Precompute averaged text embeddings for all species.
        Uses text_model + text_projection directly to avoid API differences
        across transformers versions.
        """
        species_embeddings = []
        for species in self.species:
            name = species.replace("_", " ")
            prompts = [t.format(name) for t in PROMPT_TEMPLATES]
            inputs = self.processor(text=prompts, return_tensors="pt", padding=True, truncation=True)

            text_out = self.model.text_model(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
            )
            text_feats = self.model.text_projection(text_out.pooler_output)
            text_feats = F.normalize(text_feats, dim=-1)

            averaged = text_feats.mean(dim=0)
            averaged = F.normalize(averaged, dim=-1)
            species_embeddings.append(averaged)

        return torch.stack(species_embeddings)  # (num_species, embed_dim)

    @torch.no_grad()
    def predict(self, image: Image.Image, top_k: int = 3) -> dict:
        inputs = self.processor(images=image.convert("RGB"), return_tensors="pt")

        image_out = self.model.vision_model(pixel_values=inputs["pixel_values"])
        image_feats = self.model.visual_projection(image_out.pooler_output)
        image_feats = F.normalize(image_feats, dim=-1)

        logits = 100.0 * (image_feats @ self.text_embeddings.T)
        probs = logits.softmax(dim=-1)[0]

        top_probs, top_idx = probs.topk(min(top_k, len(self.species)))

        predictions = []
        for prob, idx in zip(top_probs.tolist(), top_idx.tolist()):
            name = self.species[idx]
            predictions.append({
                "species": name.replace("_", " ").title(),
                "confidence": round(prob, 4),
                "metadata": self.metadata.get(_normalize(name), {}),
            })

        uncertain = predictions[0]["confidence"] < UNCERTAIN_THRESHOLD
        return {
            "predictions": predictions,
            "uncertain": uncertain,
            "message": "Low confidence — this may not be a fish, or the species isn't in our database." if uncertain else None,
        }
