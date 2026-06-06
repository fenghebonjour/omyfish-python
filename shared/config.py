import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings:
    checkpoint_path: str = os.getenv(
        "CHECKPOINT_PATH", str(_REPO_ROOT / "checkpoints" / "best.pt")
    )
    metadata_path: str = os.getenv(
        "METADATA_PATH", str(_REPO_ROOT / "data" / "metadata" / "fish_info.json")
    )
    database_url: str = os.getenv("DATABASE_URL", "")
    env: str = os.getenv("ENV", "development")


settings = Settings()
