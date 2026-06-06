from fastapi import APIRouter
from apps.omyfish_api.db.engine import db_ready

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "db": db_ready()}
