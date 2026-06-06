from functools import lru_cache

from shared.config import settings


@lru_cache(maxsize=1)
def get_ai_service():
    from services.fish_ai.service import FishAIService
    return FishAIService.build(settings.checkpoint_path, settings.metadata_path)


@lru_cache(maxsize=1)
def get_gis_service():
    from services.gis_service.service import GISService
    return GISService()


def get_obs_repo():
    from apps.omyfish_api.db.engine import ensure_db
    from apps.omyfish_api.repositories.observation_repository import ObservationRepository
    ensure_db()
    return ObservationRepository()
