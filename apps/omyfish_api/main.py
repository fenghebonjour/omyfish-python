import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.omyfish_api.db.engine import ensure_db
from apps.omyfish_api.routes import health, species, observations

app = FastAPI(title="OMyFish API", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(health.router)
app.include_router(species.router)
app.include_router(observations.router)


@app.on_event("startup")
def startup():
    ensure_db()
