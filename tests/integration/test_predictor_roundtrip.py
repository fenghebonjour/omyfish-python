"""Checkpoint contract test: what train.py saves, FishPredictor must load.

Uses a tiny untrained backbone so it runs CPU-fast without the real best.pt.
"""
import json

import pytest
import torch
from PIL import Image

from services.fish_ai.model.classifier import build_model
from services.fish_ai.predictors.efficientnet import FishPredictor

CONFIG = {
    "model": {"architecture": "resnet18", "num_classes": 3, "pretrained": False, "dropout": 0.1},
    "data": {"image_size": 64},
}
CLASSES = ["Brook Trout", "northern_pike", "walleye"]
METADATA = [
    # Hyphenated on purpose: must still match the "Brook Trout" class name
    {"species": "Brook-Trout", "scientific_name": "Salvelinus fontinalis"},
    {"species": "Walleye", "scientific_name": "Sander vitreus"},
]


@pytest.fixture(scope="module")
def predictor(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ckpt")
    model = build_model(CONFIG)
    torch.save(
        {"config": CONFIG, "model_state_dict": model.state_dict()},
        tmp / "best.pt",
    )
    (tmp / "classes.json").write_text(json.dumps(CLASSES))
    (tmp / "fish_info.json").write_text(json.dumps(METADATA))
    return FishPredictor(
        str(tmp / "best.pt"), metadata_path=str(tmp / "fish_info.json"), device="cpu"
    )


def test_loads_classes_from_sibling_json(predictor):
    assert predictor.classes == CLASSES


def test_predict_structure(predictor):
    result = predictor.predict(Image.new("RGB", (80, 60)), top_k=3)
    preds = result["predictions"]
    assert len(preds) == 3
    confs = [p["confidence"] for p in preds]
    assert confs == sorted(confs, reverse=True)
    assert sum(confs) == pytest.approx(1.0, abs=0.01)
    assert {p["species"] for p in preds} == set(CLASSES)


def test_top_k_capped_at_class_count(predictor):
    result = predictor.predict(Image.new("RGB", (80, 60)), top_k=10)
    assert len(result["predictions"]) == 3


def test_metadata_matched_via_name_normalization(predictor):
    result = predictor.predict(Image.new("RGB", (80, 60)), top_k=3)
    by_species = {p["species"]: p["metadata"] for p in result["predictions"]}
    # "Brook Trout" class ↔ "Brook-Trout" metadata key
    assert by_species["Brook Trout"]["scientific_name"] == "Salvelinus fontinalis"
    assert by_species["walleye"]["scientific_name"] == "Sander vitreus"
    # No metadata entry for northern_pike → empty dict, not a crash
    assert by_species["northern_pike"] == {}


def test_uncertain_flag_matches_threshold(predictor):
    result = predictor.predict(Image.new("RGB", (80, 60)))
    top = result["predictions"][0]["confidence"]
    assert result["uncertain"] == (top < 0.30)
    if result["uncertain"]:
        assert result["message"]
    else:
        assert result["message"] is None
