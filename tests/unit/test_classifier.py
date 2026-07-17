import torch

from services.fish_ai.model.classifier import FishClassifier, build_model

# Small untrained backbone keeps this CPU-fast and download-free.
TINY = {"model": {"architecture": "resnet18", "num_classes": 5, "pretrained": False, "dropout": 0.3}}


def test_forward_output_shape():
    model = build_model(TINY)
    model.eval()
    with torch.no_grad():
        logits = model(torch.randn(2, 3, 64, 64))
    assert logits.shape == (2, 5)


def test_embed_is_l2_normalized():
    model = FishClassifier("resnet18", num_classes=5, pretrained=False)
    model.eval()
    with torch.no_grad():
        emb = model.embed(torch.randn(3, 3, 64, 64))
    norms = emb.norm(dim=1)
    assert torch.allclose(norms, torch.ones(3), atol=1e-5)
