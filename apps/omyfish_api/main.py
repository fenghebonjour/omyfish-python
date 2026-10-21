import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.omyfish_api.db.engine import ensure_db
from apps.omyfish_api.routes import admin, auth, billing, health, observations, shop, species, users

logger = logging.getLogger(__name__)

app = FastAPI(title="OMyFish API", version="2.0.0")
# Set ALLOWED_ORIGINS (comma-separated) in production; * is the dev default.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# Catches anything a route's own try/except doesn't already turn into a clean
# HTTPException, so callers get structured JSON instead of FastAPI's raw default 500
# (BACKLOG.md item B, WEAKNESS_AUDIT.md §2.2). Doesn't intercept HTTPException — Starlette
# resolves that via its own more-specific, already-registered handler first.
@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s", request.url.path)
    return JSONResponse(status_code=500, content={"error": "An unexpected error occurred."})

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(billing.router)
app.include_router(admin.router)
app.include_router(health.router)
app.include_router(species.router)
app.include_router(observations.router)
app.include_router(shop.router)


@app.on_event("startup")
def startup():
    ensure_db()
