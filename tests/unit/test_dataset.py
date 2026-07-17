import numpy as np
import pytest
from PIL import Image

from services.fish_ai.training.dataset import FishDataset


def _make_images(class_dir, count):
    class_dir.mkdir(parents=True)
    for i in range(count):
        Image.new("RGB", (4, 4), color=(i * 20 % 255, 0, 0)).save(class_dir / f"img{i}.jpg")


@pytest.fixture
def flat_root(tmp_path):
    """Auto-split layout: root/<class>/*.jpg — 10 bass, 5 pike."""
    _make_images(tmp_path / "bass", 10)
    _make_images(tmp_path / "pike", 5)
    return tmp_path


@pytest.fixture
def presplit_root(tmp_path):
    """Pre-split layout: root/train|val/<class>/*.jpg."""
    _make_images(tmp_path / "train" / "bass", 4)
    _make_images(tmp_path / "train" / "pike", 4)
    _make_images(tmp_path / "val" / "bass", 2)
    _make_images(tmp_path / "val" / "pike", 2)
    return tmp_path


class TestAutoSplit:
    def test_classes_sorted_and_indexed(self, flat_root):
        ds = FishDataset(str(flat_root), split="train")
        assert ds.classes == ["bass", "pike"]
        assert ds.class_to_idx == {"bass": 0, "pike": 1}

    def test_stratified_80_20_split(self, flat_root):
        train = FishDataset(str(flat_root), split="train", val_ratio=0.2)
        val = FishDataset(str(flat_root), split="val", val_ratio=0.2)
        assert len(train) == 12 and len(val) == 3
        # Stratified: each split keeps the 2:1 class ratio
        train_labels = [lbl for _, lbl in train.samples]
        val_labels = [lbl for _, lbl in val.samples]
        assert train_labels.count(0) == 8 and train_labels.count(1) == 4
        assert val_labels.count(0) == 2 and val_labels.count(1) == 1

    def test_split_is_deterministic_and_disjoint(self, flat_root):
        train = FishDataset(str(flat_root), split="train", seed=42)
        train2 = FishDataset(str(flat_root), split="train", seed=42)
        val = FishDataset(str(flat_root), split="val", seed=42)
        assert train.samples == train2.samples
        assert set(p for p, _ in train.samples).isdisjoint(p for p, _ in val.samples)


class TestPreSplit:
    def test_layout_detected(self, presplit_root):
        train = FishDataset(str(presplit_root), split="train")
        val = FishDataset(str(presplit_root), split="val")
        assert len(train) == 8 and len(val) == 4
        assert train.classes == ["bass", "pike"]


def test_getitem_returns_image_and_label(flat_root):
    ds = FishDataset(str(flat_root), split="train")
    image, label = ds[0]
    assert isinstance(image, np.ndarray) and image.shape == (4, 4, 3)
    assert label in (0, 1)


def test_sample_weights_inverse_to_class_frequency(flat_root):
    ds = FishDataset(str(flat_root), split="train", val_ratio=0.2)
    weights = ds.sample_weights()
    assert len(weights) == len(ds)
    by_label = {}
    for w, (_, lbl) in zip(weights.tolist(), ds.samples):
        by_label.setdefault(lbl, w)
    # pike (minority, 4 train samples) must outweigh bass (8 train samples)
    assert by_label[1] > by_label[0]
    assert by_label[1] == pytest.approx(2 * by_label[0])
