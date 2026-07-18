"""FishAIService gate behavior — fake gate/predictor, no CLIP download."""
import pytest
from PIL import Image

import services.fish_ai.predictors.fish_gate as fish_gate_module
from services.fish_ai.service import FishAIService

IMG = Image.new("RGB", (16, 16))


class FakePredictor:
    def __init__(self):
        self.calls = 0

    def predict(self, image, top_k=3):
        self.calls += 1
        return {"predictions": [{"species": "walleye", "confidence": 0.9}], "uncertain": False}


class FakeGate:
    def __init__(self, verdict):
        self.verdict = verdict

    def is_fish(self, image):
        return self.verdict, 0.99 if self.verdict else 0.01


@pytest.fixture
def service():
    return FishAIService(FakePredictor(), mode="trained")


def test_non_fish_rejected_without_calling_predictor(service):
    service._gate = FakeGate(False)
    result = service.predict(IMG)
    assert result["is_fish"] is False
    assert result["predictions"] == []
    assert result["uncertain"] is True
    assert "fish" in result["message"]
    assert service._predictor.calls == 0


def test_fish_passes_gate_and_reaches_predictor(service):
    service._gate = FakeGate(True)
    result = service.predict(IMG)
    assert result["is_fish"] is True
    assert result["predictions"][0]["species"] == "walleye"
    assert "gate_unavailable" not in result
    assert service._predictor.calls == 1


def test_gate_load_failure_sets_gate_unavailable(service, monkeypatch):
    class Boom:
        def __init__(self):
            raise RuntimeError("no network")

    monkeypatch.setattr(fish_gate_module, "FishGate", Boom)
    result = service.predict(IMG)
    assert result["is_fish"] is True
    assert result["gate_unavailable"] is True
    assert result["predictions"][0]["species"] == "walleye"


def test_gate_load_failure_is_not_retried(service, monkeypatch):
    attempts = []

    class Boom:
        def __init__(self):
            attempts.append(1)
            raise RuntimeError("no network")

    monkeypatch.setattr(fish_gate_module, "FishGate", Boom)
    service.predict(IMG)
    service.predict(IMG)
    assert len(attempts) == 1
    assert service._gate_failed is True
