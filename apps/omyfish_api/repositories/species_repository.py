import json
from pathlib import Path
from typing import Optional


class SpeciesRepository:

    def __init__(self, metadata_path: str = "data/metadata/fish_info.json"):
        fish_list = json.loads(Path(metadata_path).read_text())
        self._data = {_normalize(f["species"]): f for f in fish_list}

    def get_by_name(self, name: str) -> Optional[dict]:
        return self._data.get(_normalize(name))

    def list_all(self) -> list:
        return list(self._data.values())


def _normalize(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")
