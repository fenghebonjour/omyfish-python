# OMyFish — Architecture Refactor Plan

## Current State Analysis

### What exists

| File | Concerns mixed inside |
|---|---|
| `app/api.py` | Routes + raw SQL + GeoJSON build + EXIF extraction + predictor loading |
| `app/main.py` (Streamlit) | UI + direct DB writes (raw SQL) + map rendering + EXIF extraction |
| `app/database.py` | Engine + DDL + SQLite/PostGIS dual-path |
| `app/gis.py` | Single function: `extract_exif_gps()` |
| `app/clip_predictor.py` | CLIP zero-shot AI predictor |
| `src/` | Training pipeline (model, dataset, train, evaluate, predict, transforms) |

### Key problems

1. **No service layer** — routes call predictors and hit the DB directly
2. **No repository layer** — raw SQL strings live inside routes and Streamlit pages
3. **GIS is vestigial** — one function; GeoJSON built inline in routes
4. **Two predictors are disconnected** — `FishPredictor` and `CLIPFishPredictor` have the same `predict()` interface but no shared contract
5. **Config is hardcoded** — DB URL, thresholds, checkpoint paths scattered across files
6. **PostGIS already partially wired** — `geom GEOGRAPHY(POINT,4326)` is in `init_db()` but created through raw DDL, no migrations

---

## 1. Target Folder Structure

```
omyfish/

├── apps/
│   ├── omyfish-api/                  # FastAPI backend
│   │   ├── main.py                   # App factory + middleware
│   │   ├── routes/
│   │   │   ├── observations.py
│   │   │   ├── species.py
│   │   │   ├── gis.py
│   │   │   └── health.py
│   │   ├── repositories/
│   │   │   ├── observation_repository.py
│   │   │   └── species_repository.py
│   │   └── db/
│   │       ├── engine.py             # SQLAlchemy engine setup
│   │       └── migrations/           # Alembic migrations
│   │
│   ├── omyfish-web/                  # Streamlit frontend
│   │   ├── main.py
│   │   └── pages/
│   │       ├── identify.py
│   │       └── map.py
│   │
│   └── omyfish-admin/               # Placeholder — future admin dashboard
│       └── __init__.py
│
├── services/
│   ├── fish-ai/                      # All ML logic
│   │   ├── service.py                # FishAIService (unified interface)
│   │   ├── predictors/
│   │   │   ├── base.py               # BaseFishPredictor ABC
│   │   │   ├── efficientnet.py       # FishPredictor (trained model)
│   │   │   └── clip.py               # CLIPFishPredictor (zero-shot)
│   │   ├── training/                 # move src/train.py, dataset.py, transforms.py here
│   │   │   ├── train.py
│   │   │   ├── dataset.py
│   │   │   ├── evaluate.py
│   │   │   └── transforms.py
│   │   ├── model/                    # move src/model.py here
│   │   │   └── classifier.py
│   │   └── tests/
│   │
│   ├── gis-service/                  # All geospatial logic
│   │   ├── service.py                # GISService
│   │   ├── exif.py                   # extract_exif_gps (move from app/gis.py)
│   │   ├── geojson.py                # GeoJSON builders
│   │   ├── spatial_queries.py        # PostGIS spatial queries
│   │   └── tests/
│   │
│   ├── ingestion-service/            # Placeholder — external data sources
│   │   ├── interfaces.py             # ObservationSource ABC
│   │   └── __init__.py
│   │
│   └── analytics-service/            # Placeholder — heatmaps, distributions
│       ├── interfaces.py             # AnalyticsService ABC
│       └── __init__.py
│
├── shared/
│   ├── models/
│   │   ├── observation.py            # SQLAlchemy ORM + Pydantic schemas
│   │   ├── species.py
│   │   ├── user.py
│   │   └── location.py
│   ├── schemas/
│   │   ├── observation.py            # Request/response Pydantic models
│   │   ├── prediction.py
│   │   └── geojson.py
│   ├── constants/
│   │   └── thresholds.py             # UNCERTAIN_THRESHOLD etc.
│   └── utils/
│       └── ids.py                    # new_id(), UUID helpers
│
├── data/
│   ├── raw/
│   ├── processed/
│   ├── training/
│   ├── metadata/
│   └── exports/
│
├── infrastructure/
│   ├── docker/
│   │   ├── docker-compose.yml        # move from root
│   │   ├── docker-compose.prod.yml
│   │   └── Dockerfile                # move from root
│   └── k8s/                          # Future Kubernetes manifests
│
├── configs/
│   ├── development.yaml
│   ├── production.yaml
│   └── training.yaml                 # move config.yaml here
│
├── docs/
│   └── ARCHITECTURE_REFACTOR.md     # this file
│
└── research/                         # notebooks/, scripts/
    ├── notebooks/
    └── scripts/
```

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                     CLIENT LAYER                        │
│                                                         │
│   omyfish-web (Streamlit)    omyfish-admin (future)     │
└────────────────┬────────────────────────────────────────┘
                 │ HTTP
┌────────────────▼────────────────────────────────────────┐
│                    omyfish-api (FastAPI)                 │
│                                                         │
│  routes/           repositories/                        │
│  ├── observations  ├── ObservationRepository ──────────┐│
│  ├── species       └── SpeciesRepository               ││
│  ├── gis                                               ││
│  └── health                                            ││
└──────┬────────────────────────────────────────────────┬─┘
       │ calls                                          │ ORM
┌──────▼──────────────────┐          ┌─────────────────▼──┐
│    services/fish-ai     │          │   PostgreSQL        │
│                         │          │   + PostGIS         │
│  FishAIService          │          │                     │
│  ├── EfficientNet mode  │          │  observations       │
│  └── CLIP zero-shot     │          │  (geom GEOGRAPHY)   │
└─────────────────────────┘          └────────────────────┘
┌──────────────────────────┐
│   services/gis-service   │
│                          │
│  GISService              │
│  ├── EXIF extraction     │
│  ├── GeoJSON building    │
│  └── spatial queries ───────────────────────────────────┐
└──────────────────────────┘                              │
                                                          │
                                              PostGIS spatial
                                              functions (ST_*)
```

---

## 3. Domain Model Definitions

### Observation (core entity)

```python
# shared/models/observation.py

from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, String, Float, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from geoalchemy2 import Geography
from shared.db import Base

class Observation(Base):
    __tablename__ = "observations"

    id: UUID               = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    species_name: str      = Column(String, nullable=False)
    scientific_name: str   = Column(String)
    confidence: float      = Column(Float, nullable=False)
    timestamp: datetime    = Column(DateTime(timezone=True), default=datetime.utcnow)
    latitude: float        = Column(Float)
    longitude: float       = Column(Float)
    geom                   = Column(Geography("POINT", srid=4326))  # PostGIS
    image_url: str         = Column(Text)
    user_id: str           = Column(String)
    source: str            = Column(String, default="upload")
```

### Species (knowledge entity)

```python
# shared/models/species.py

from pydantic import BaseModel
from typing import Optional

class Species(BaseModel):
    name: str
    scientific_name: Optional[str]
    habitat: Optional[str]
    diet: Optional[str]
    max_size_cm: Optional[float]
    conservation_status: Optional[str]
    description: Optional[str]
    fun_fact: Optional[str]
```

### Location (value object)

```python
# shared/models/location.py

from pydantic import BaseModel
from typing import Optional

class Coordinates(BaseModel):
    latitude: float
    longitude: float

class GeoPoint(BaseModel):
    coordinates: Coordinates
    srid: int = 4326
    source: str  # "manual" | "exif" | "gps"
```

### Prediction (value object — never persisted directly)

```python
# shared/schemas/prediction.py

from pydantic import BaseModel
from typing import Optional, List
from shared.models.species import Species

class PredictionResult(BaseModel):
    species: str
    confidence: float
    metadata: Optional[Species]

class PredictionResponse(BaseModel):
    predictions: List[PredictionResult]
    uncertain: bool
    message: Optional[str]
    top_species: str         # convenience: predictions[0].species
    top_confidence: float    # convenience: predictions[0].confidence
```

### Events (domain events)

```python
# shared/events.py

from pydantic import BaseModel
from uuid import UUID
from datetime import datetime

class DomainEvent(BaseModel):
    event_id: UUID
    occurred_at: datetime

class ObservationCreated(DomainEvent):
    observation_id: UUID
    species_name: str
    latitude: float
    longitude: float
    source: str

class SpeciesPredicted(DomainEvent):
    species_name: str
    confidence: float
    uncertain: bool

class ObservationValidated(DomainEvent):
    observation_id: UUID
    validated_by: str
    is_correct: bool
```

---

## 4. Service Interfaces

### Fish AI Service

```python
# services/fish-ai/service.py

from abc import ABC, abstractmethod
from typing import List
from PIL import Image
from shared.schemas.prediction import PredictionResponse, PredictionResult
from shared.models.species import Species

class BaseFishPredictor(ABC):
    @abstractmethod
    def predict(self, image: Image.Image, top_k: int = 3) -> PredictionResponse:
        ...

class FishAIService:
    """
    Unified entry point for AI inference.
    Delegates to EfficientNet if checkpoint exists, CLIP otherwise.
    """

    def __init__(self, predictor: BaseFishPredictor):
        self._predictor = predictor

    def predict_species(self, image: Image.Image) -> PredictionResponse:
        return self._predictor.predict(image, top_k=1)

    def get_top_predictions(self, image: Image.Image, top_k: int = 3) -> PredictionResponse:
        return self._predictor.predict(image, top_k=top_k)

    def get_species_info(self, species_name: str) -> Optional[Species]:
        # Looks up the knowledge base — no model inference needed
        ...
```

### GIS Service

```python
# services/gis-service/service.py

from abc import ABC
from typing import Optional, List
from PIL import Image
from shared.models.location import Coordinates, GeoPoint
from shared.models.observation import Observation

class GISService:

    def create_observation_point(self, lat: float, lon: float, source: str) -> GeoPoint:
        ...

    def extract_gps_from_image(self, image: Image.Image) -> Optional[Coordinates]:
        ...

    def export_geojson(self, observations: List[Observation]) -> dict:
        ...

    def observations_within_radius(
        self,
        center: Coordinates,
        radius_m: float,
    ) -> List[Observation]:
        # Delegates to spatial_queries.py (PostGIS ST_DWithin)
        ...

    def nearest_observation(self, point: Coordinates) -> Optional[Observation]:
        ...
```

### Ingestion Service (placeholder)

```python
# services/ingestion-service/interfaces.py

from abc import ABC, abstractmethod
from typing import List, Iterator
from shared.models.observation import Observation

class ObservationSource(ABC):
    """Interface for external observation data providers."""

    @abstractmethod
    def fetch_observations(self) -> Iterator[Observation]:
        ...

    @abstractmethod
    def source_name(self) -> str:
        ...

# Future implementations:
# class INaturalistSource(ObservationSource): ...
# class GBIFSource(ObservationSource): ...
# class GovernmentDatasetSource(ObservationSource): ...
```

### Analytics Service (placeholder)

```python
# services/analytics-service/interfaces.py

from abc import ABC, abstractmethod
from typing import List
from shared.models.observation import Observation

class AnalyticsService(ABC):

    @abstractmethod
    def generate_heatmap(self, observations: List[Observation]) -> dict:
        ...

    @abstractmethod
    def species_distribution(self, species_name: str) -> dict:
        ...

    @abstractmethod
    def density_estimation(self, bbox: tuple) -> dict:
        ...
```

---

## 5. Repository Interfaces

```python
# apps/omyfish-api/repositories/observation_repository.py

from abc import ABC, abstractmethod
from uuid import UUID
from typing import Optional, List
from shared.models.observation import Observation
from shared.models.location import Coordinates

class ObservationRepository(ABC):

    @abstractmethod
    def create(self, obs: ObservationCreate) -> Observation:
        ...

    @abstractmethod
    def get_by_id(self, id: UUID) -> Optional[Observation]:
        ...

    @abstractmethod
    def list(self, limit: int = 100) -> List[Observation]:
        ...

    @abstractmethod
    def list_within_radius(
        self, center: Coordinates, radius_m: float
    ) -> List[Observation]:
        ...

    @abstractmethod
    def list_as_geojson(self, limit: int = 1000) -> dict:
        ...


class SQLObservationRepository(ObservationRepository):
    """PostgreSQL/PostGIS implementation."""

    def __init__(self, session):
        self._session = session

    def create(self, obs: ObservationCreate) -> Observation:
        # Uses SQLAlchemy ORM; PostGIS geom set via ST_MakePoint
        ...

    def list_within_radius(self, center: Coordinates, radius_m: float) -> List[Observation]:
        # ST_DWithin(geom, ST_MakePoint(:lon,:lat)::geography, :radius_m)
        ...
```

```python
# apps/omyfish-api/repositories/species_repository.py

class SpeciesRepository(ABC):

    @abstractmethod
    def get_by_name(self, name: str) -> Optional[Species]:
        ...

    @abstractmethod
    def list_all(self) -> List[Species]:
        ...


class JSONSpeciesRepository(SpeciesRepository):
    """File-based implementation backed by data/metadata/fish_info.json."""
    ...
```

---

## 6. PostGIS Migration Strategy

### Current state
- `init_db()` in `app/database.py` creates the schema via raw DDL on startup
- PostGIS `geom` column already present when `DATABASE_URL` is PostgreSQL
- No migration history — schema is recreated on every `init_db()` call

### Target state

**Step 1: Add Alembic**
```bash
pip install alembic geoalchemy2
alembic init apps/omyfish-api/db/migrations
```

**Step 2: Initial migration** — captures the current schema
```python
# alembic/versions/001_initial_schema.py
def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "observations",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("species_name", sa.Text()),
        sa.Column("scientific_name", sa.Text()),
        sa.Column("confidence", sa.Float()),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("geom", Geography("POINT", srid=4326)),
        sa.Column("image_url", sa.Text()),
        sa.Column("user_id", sa.Text()),
        sa.Column("source", sa.Text(), server_default="upload"),
    )
    op.create_index("observations_geom_idx", "observations", ["geom"], postgresql_using="gist")
```

**Step 3: Drop `init_db()` DDL** — replace with `alembic upgrade head` on startup

**Step 4: Future spatial migrations are versioned**
```python
# alembic/versions/002_add_species_table.py
# alembic/versions/003_add_validated_flag.py
```

### SQLite fallback
Keep SQLite for local dev/HF Spaces with `--dev` flag. Alembic handles only the PostgreSQL path; SQLite uses a lightweight DDL shim (no migration history needed there).

---

## 7. Docker Architecture

```yaml
# infrastructure/docker/docker-compose.yml

services:

  postgis:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_DB: omyfish
      POSTGRES_USER: omyfish
      POSTGRES_PASSWORD: omyfish
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U omyfish"]

  api:
    build:
      context: ../../
      dockerfile: infrastructure/docker/Dockerfile.api
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://omyfish:omyfish@postgis:5432/omyfish
      ENV: development
    depends_on:
      postgis:
        condition: service_healthy
    command: uvicorn apps.omyfish-api.main:app --host 0.0.0.0 --port 8000 --reload

  web:
    build:
      context: ../../
      dockerfile: infrastructure/docker/Dockerfile.web
    ports:
      - "8501:8501"
    environment:
      API_URL: http://api:8000
      DATABASE_URL: postgresql://omyfish:omyfish@postgis:5432/omyfish
    depends_on:
      - api
    command: streamlit run apps/omyfish-web/main.py --server.port=8501

volumes:
  pgdata:
```

**Notes:**
- `fish-ai` is NOT a separate container for now — it runs in-process inside `api`. Extract to its own container only when GPU inference is needed at scale.
- `web` can be optionally pointed at `API_URL` instead of direct DB — this is the cleaner architecture for production.

---

## 8. Dependency Flow

```
omyfish-web  ──────────────────────────────►  omyfish-api
                                                  │
                                    ┌─────────────┼─────────────┐
                                    ▼             ▼             ▼
                              routes/      repositories/  services/
                                               │
                                    ┌──────────┴──────────┐
                                    ▼                     ▼
                              PostgreSQL             shared/models
                              + PostGIS                    │
                                                    ┌──────┴──────┐
                                                    ▼             ▼
                                             fish-ai/        gis-service/
                                                    │
                                             ┌──────┴──────┐
                                             ▼             ▼
                                     EfficientNet      CLIP zero-shot
                                     (checkpoints/)    (HuggingFace Hub)

Dependency rules:
  shared/      ← no dependencies on apps/ or services/
  services/    ← depends on shared/ only
  apps/        ← depends on services/ and shared/
  routes/      ← depends on repositories/ and services/ (never on DB directly)
  repositories/← depends on shared/models/ and DB session
```

---

## 9. API Redesign

### Route layout

```
GET  /health

POST /species/predict              # image → PredictionResponse
GET  /species/{name}               # species metadata lookup

POST /observations                 # create from manual input
GET  /observations                 # list, with ?limit=
GET  /observations/{id}            # single observation
GET  /observations/geojson         # FeatureCollection for map

GET  /observations/nearby          # ?lat=&lon=&radius_m=
```

### Request/response contracts

```python
# POST /species/predict
# Request: multipart/form-data — file=<image>, top_k=3
# Response:
{
  "predictions": [
    {"species": "Atlantic Salmon", "confidence": 0.87, "metadata": {...}},
    ...
  ],
  "uncertain": false,
  "message": null,
  "top_species": "Atlantic Salmon",
  "top_confidence": 0.87
}

# POST /observations
# Request body:
{
  "species_name": "Atlantic Salmon",
  "scientific_name": "Salmo salar",
  "confidence": 0.87,
  "latitude": 47.5,
  "longitude": -52.8,
  "source": "manual"
}
# Response:
{
  "id": "uuid",
  "status": "created"
}

# GET /observations/geojson
# Response: GeoJSON FeatureCollection (RFC 7946)
```

### Design rules for routes
- Routes must only call services and repositories — never the DB directly
- All SQL lives in repositories
- All AI logic lives in `FishAIService`
- All GIS logic lives in `GISService`

---

## 10. Incremental Refactoring Plan

Priority: **never break the running app between phases.**

### Phase 1 — Folder restructure (no logic changes)
*Risk: Low. Pure file moves + import updates.*

1. Create new directory skeleton
2. Move files to new locations:
   - `app/clip_predictor.py` → `services/fish-ai/predictors/clip.py`
   - `src/predict.py` → `services/fish-ai/predictors/efficientnet.py`
   - `src/model.py` → `services/fish-ai/model/classifier.py`
   - `src/train.py`, `dataset.py`, `transforms.py`, `evaluate.py` → `services/fish-ai/training/`
   - `app/gis.py` → `services/gis-service/exif.py`
   - `app/api.py` → `apps/omyfish-api/main.py` (minimal, still monolithic for now)
   - `streamlit_app.py` → `apps/omyfish-web/main.py`
   - `app/database.py` → `apps/omyfish-api/db/engine.py`
   - `configs/config.yaml` → `configs/training.yaml`
3. Update all import paths
4. Update `Makefile` and `docker-compose.yml` paths
5. **Verify:** `make api` and `make app` still work

### Phase 2 — Service layer for AI
*Risk: Low. Wraps existing code, no SQL changes.*

1. Create `services/fish-ai/predictors/base.py` with `BaseFishPredictor` ABC
2. Make `CLIPFishPredictor` and `FishPredictor` implement it
3. Create `services/fish-ai/service.py` with `FishAIService` wrapping both
4. Add a factory function: `build_predictor(checkpoint_path) -> BaseFishPredictor`
5. Update `apps/omyfish-api/main.py` and `apps/omyfish-web/main.py` to use `FishAIService`
6. **Verify:** predictions still work in both CLIP and trained modes

### Phase 3 — Repository layer
*Risk: Medium. Touches all DB access.*

1. Create `shared/models/observation.py` — SQLAlchemy ORM model
2. Create `apps/omyfish-api/repositories/observation_repository.py`
3. Create `apps/omyfish-api/repositories/species_repository.py` (JSON-backed)
4. Replace `_insert_observation()` in `main.py` (api) with `ObservationRepository.create()`
5. Replace raw SQL queries in list/geojson routes with repository calls
6. Replace raw SQL in Streamlit app with repository calls
7. **Verify:** saving and listing observations works

### Phase 4 — GIS service + shared schemas
*Risk: Low.*

1. Create `services/gis-service/service.py` with `GISService`
2. Move EXIF extraction, GeoJSON building into it
3. Create `shared/schemas/prediction.py`, `shared/schemas/observation.py`
4. Replace inline `ObservationIn` Pydantic model in routes with shared schema
5. **Verify:** `/identify-fish` and `/observations/geojson` endpoints still work

### Phase 5 — API routes split
*Risk: Low.*

1. Split `apps/omyfish-api/main.py` routes into `routes/observations.py`, `routes/species.py`, `routes/gis.py`, `routes/health.py`
2. Wire them up in `main.py` via `app.include_router(...)`
3. **Verify:** all endpoints still respond

### Phase 6 — Config management
*Risk: Low.*

1. Add `pydantic-settings` dependency
2. Create `configs/development.yaml` and `configs/production.yaml`
3. Replace scattered hardcoded values (DB URL, thresholds, checkpoint paths) with config-loaded values
4. Support: local (yaml), docker (env vars), cloud (env vars)
5. **Verify:** app starts cleanly in both modes

### Phase 7 — Placeholder services + events
*Risk: None (new files only).*

1. Create `services/ingestion-service/interfaces.py`
2. Create `services/analytics-service/interfaces.py`
3. Create `shared/events.py` with `ObservationCreated`, `SpeciesPredicted`, `ObservationValidated`
4. Emit `ObservationCreated` from `ObservationRepository.create()` (logged only, no queue yet)

### Phase 8 — Alembic migrations
*Risk: Medium (DB schema management change).*

1. Install `alembic` and `geoalchemy2`
2. `alembic init apps/omyfish-api/db/migrations`
3. Generate initial migration from current schema
4. Replace `init_db()` call with `alembic upgrade head` in API startup
5. **Verify:** fresh `docker-compose up` creates schema from migrations

### Phase 9 — Docker refactor
*Risk: Low.*

1. Move `Dockerfile` to `infrastructure/docker/`
2. Split into `Dockerfile.api` and `Dockerfile.web` (they're the same image today, which wastes space)
3. Update `docker-compose.yml` to `infrastructure/docker/docker-compose.yml`
4. Update `Makefile` paths
5. **Verify:** `docker-compose up` brings up all services

---

## Implementation Order Summary

| Phase | Work | Risk | Breaks MVP? |
|---|---|---|---|
| 1 | Folder restructure | Low | No |
| 2 | Fish AI service layer | Low | No |
| 3 | Repository layer | Medium | No |
| 4 | GIS service + shared schemas | Low | No |
| 5 | API routes split | Low | No |
| 6 | Config management | Low | No |
| 7 | Placeholder services + events | None | No |
| 8 | Alembic migrations | Medium | No |
| 9 | Docker refactor | Low | No |

Total: 9 phases, each independently verifiable, zero downtime.

---

*Generated: 2026-06-06 | Status: Ready for implementation*
