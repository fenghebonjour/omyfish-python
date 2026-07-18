# OMyFish Python
Startup Strategies & Architecture Map
github.com/fenghebonjour/omyfish-python
Python 3.11  ·  PyTorch  ·  EfficientNet-B3 + CLIP  ·  FastAPI  ·  Streamlit  ·  PostGIS  ·  Folium

## Project Family
This repo is the AI-first Python origin of the OMyFish platform. Two enterprise re-architectures exist in parallel, and a shared AI microservice (omyfish-ai) now wraps this repo's EfficientNet-B3 predictor for reuse by all three.

| Repo | Stack | Architecture |
| --- | --- | --- |
| omyfish-python | Python 3.11 - PyTorch - FastAPI - Streamlit | Monolith -> service-oriented |
| omyfish-dotnet | .NET 10 - ASP.NET Core - EF Core - YARP | Clean Architecture + CQRS (MediatR) |
| omyfish-java | Java 21 - Spring Boot 3.x - Hibernate - Spring AMQP | Hexagonal Architecture + Event-Driven |
| omyfish-ai | Python 3.11 - PyTorch - FastAPI | Standalone AI microservice -- shared by all three |

> **Note omyfish-ai wraps the EfficientNet-B3 predictor from this repo (POST /predict) and hosts the Bite Score fishing-timing forecast engine (GET /bite-score/*), both consumed by omyfish-dotnet and omyfish-java. All four projects share the same PostgreSQL/PostGIS, RabbitMQ, and MinIO infrastructure stack.**

## What It Does
OMyFish — Your AI Fishing Companion. When, Where, What you catch. Check the Timing tab for the best hours to fish, photograph a fish for an instant species identification with ecological details, log the sighting with GPS coordinates, and track all observations on a world map.
Live demo: huggingface.co/spaces/fenghebonjour/omyfish
### Identify
Top-3 candidate species with confidence scores and full ecological profile
Scientific name, habitat, diet, maximum recorded size
Conservation status, color-coded Least Concern through Endangered
13 North American freshwater species at 83.6% validation accuracy on EfficientNet-B3
Zero-shot CLIP fallback covers cases where no trained checkpoint is present
CLIP fish gate rejects non-fish photos with a friendly "not a fish" message instead of a bogus species guess

### Log observations
GPS coordinates extracted automatically from photo EXIF data when available
Manual entry for photos without GPS metadata
Stored in PostgreSQL (Supabase) with species, confidence, coordinates, timestamp
Optional user accounts: log in and new sightings are tagged with your user ID

### Map
All saved observations on an interactive world map (Folium)
Click a marker for species name, confidence, and timestamp

### Timing
Hourly Bite Score forecast (0-100) up to 14 days ahead, per location and species
Daily outlook strip, Major/Minor peak windows, six-factor breakdown, storm safety alerts
Location comes from browser geolocation automatically (asks permission once); manual entry as override
Rendered by apps/omyfish_web/timing.py from the shared omyfish-ai service

### Accounts & auth
Register / Log in tabs in the Streamlit sidebar; sessions persist per browser via cookies (each visitor gets their own session — nothing shared between browsers)
API auth is JWT-based: bcrypt-hashed passwords, POST /auth/login returns a bearer token
Everything still works logged out — accounts only add ownership tagging on saved sightings

### API (FastAPI backend)
Routes are split into modular routers (auth, users, species, observations, health) with a repository layer underneath — no longer a monolithic main.py.

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | /predict | Raw top-K identification |
| POST | /identify-fish | Identify + extract GPS + optionally save |
| POST | /observations | Save a sighting (tagged to the current user when authenticated) |
| GET | /observations | List all stored sightings |
| GET | /observations/geojson | GeoJSON export for external GIS tools |
| POST | /auth/register | Create an account |
| POST | /auth/login | Get a JWT bearer token |
| GET | /auth/me | Current user from token |
| GET | /users | List users |
| DELETE | /users/{user_id} | Delete a user |
| GET | /health | Service health check |

## Two Operating Modes

| Mode | When Active | Model |
| --- | --- | --- |
| Fine-tuned | checkpoints/best.pt present | EfficientNet-B3 trained on your dataset (83.6% val accuracy on 13 species) |
| Zero-shot demo | No checkpoint | openai/clip-vit-base-patch32 |

Zero-shot requires no data or training. Fine-tuned mode delivers higher accuracy on the species you train on, and is the mode used once checkpoints/best.pt exists.

> **No training needed for fine-tuned mode: the pre-trained checkpoint (EfficientNet-B3, 13 species) is published as a GitHub release. `gh release download model-v1 --dir checkpoints/` fetches best.pt + classes.json and the app switches to fine-tuned mode on next start. Train yourself (Option 3) only to change species coverage or improve accuracy.**

## Three Ways to Run This Repo

|  | Streamlit + FastAPI (local) | Docker Compose | Hybrid (train + serve) |
| --- | --- | --- | --- |
| Debugger | Full (VS Code / PyCharm) | None (logs only) | Full while serving |
| Setup effort | Low |  | Medium |
| GPU needed | Only for training |  | Yes, for training |
| DB | SQLite fallback | Postgres (Supabase) | Either |
| Timing tab (Bite Score) | Needs ../omyfish-ai running (BITE_SERVICE_URL, default localhost:8000) | Root Dockerfile bundles omyfish-ai; the compose stack joins its omyfish-shared network (start ../omyfish-ai first) | Same as local |
| Best for | First demo, exploring code | Closest to HF Spaces deploy | Training a custom model then serving it |

## Option 1 -- Streamlit + FastAPI (Quickest Local Start)

> `Fastest path to running`  ·  `No Docker needed`  ·  `Zero-shot works instantly`

### Prerequisites
Python 3.11+ -- confirm: python --version
pip or conda
No GPU required for zero-shot mode (CLIP runs on CPU)
GPU (CUDA) recommended for training -- not required to run the app

### Step-by-step
### Clone the repo

> **git clone https://github.com/fenghebonjour/omyfish-python cd omyfish-python**

### Install dependencies
Installs PyTorch, transformers (CLIP), Streamlit, FastAPI, and all ML deps.

> **pip install -r requirements.txt**

### Fetch the pre-trained model (optional but recommended)
Skips zero-shot mode entirely — the app starts in fine-tuned mode (83.6% val accuracy, 13 species).

> **gh release download model-v1 --dir checkpoints/**

### Launch the Streamlit UI
Starts in zero-shot mode immediately -- no training required.

> **make app          # Streamlit UI at http://localhost:8501**

### Launch the FastAPI backend (optional, separate terminal)
Run alongside or instead of the Streamlit UI to expose the REST API.

> **make api          # FastAPI at http://localhost:8000**

### Start the shared AI service for the Timing tab (optional, separate terminal)
The Timing tab (apps/omyfish_web/timing.py) fetches its Bite Score forecast from the shared omyfish-ai service -- it is not part of this repo. Identify and Map work without it; only Timing shows an error when it's absent.

> **cd ../omyfish-ai docker compose up          # -> http://localhost:8000**

> **Port clash warning make api and omyfish-ai both default to port 8000, and BITE_SERVICE_URL defaults to http://localhost:8000. Run only one of them on :8000 -- or start omyfish-ai on another port and set BITE_SERVICE_URL to match before make app.**

### Upload a fish photo
Drag and drop or browse a fish image in the Streamlit UI. The app shows top-3 species with confidence scores and metadata from the 39-species knowledge base.

> **Note Without DATABASE_URL set, the app falls back to SQLite for observation storage -- fine for local exploration, but use Supabase Postgres for anything persistent or shared.**

| Advantages ✓  Zero-shot works with no data or training ✓  Fastest possible startup -- one command ✓  No Docker required ✓  Pre-trained checkpoint one `gh release download` away ✓  39-species knowledge base included | Drawbacks ✗  CLIP zero-shot accuracy is lower than fine-tuned EfficientNet ✗  SQLite fallback isn't suitable for shared/production use ✗  Timing tab needs ../omyfish-ai running separately (and :8000 clashes with make api) |
| --- | --- |

> **Best for First demo, exploring the codebase, or providing the AI inference layer that omyfish-ai wraps for the Java and .NET enterprise stacks.**

## Option 2 -- Docker Compose (Closest to Deployed)

> `Single docker image`  ·  `No debugger`  ·  `Matches HF Spaces deploy`

### Run with the root Dockerfile (the HF Spaces image)
The root Dockerfile is the exact HuggingFace Spaces image: Streamlit on port 7860, with the shared omyfish-ai service **bundled inside** -- downloaded from GitHub main at build time into /ai and served internally on 127.0.0.1:8000 (BITE_SERVICE_URL is preset; DISABLE_FISH_ID=1 keeps the bundled copy bite-score-only). The Timing tab therefore works out of the box in this image; rebuilding refreshes the bundled bite engine. The image installs **CPU-only PyTorch wheels** -- the full CUDA stack blew past the HF Spaces build timeout, and inference doesn't need it.

> **docker build -t omyfish-python . docker run -p 7860:7860 \ -e DATABASE_URL=postgresql://... \ omyfish-python # Streamlit at http://localhost:7860**

### Or via docker-compose.yml

> **cd ../omyfish-ai && docker compose up -d   # start the bite-score service first cd ../omyfish-python && docker compose up # Streamlit at :8501, FastAPI at :8001, PostGIS at :5432**

> **How the Timing tab is wired The app/web service joins the external omyfish-shared network (created by ../omyfish-ai's compose) and sets BITE_SERVICE_URL=http://ai-service:8000, so the Timing tab reaches the bite-score service container-to-container. Start ../omyfish-ai first -- the network is declared external, so this stack won't start without it. The FastAPI backend is published on host :8001 (host :8000 belongs to the shared omyfish-ai service).**

| Advantages ✓  Single image -- same Dockerfile used by HuggingFace Spaces deploy ✓  Reproducible environment, no local Python version conflicts ✓  Easy to pass DATABASE_URL and other secrets via env vars | Drawbacks ✗  No breakpoints -- container logs only ✗  Slower iteration than running Streamlit/FastAPI directly ✗  Image rebuild needed after every code change |
| --- | --- |

> **Best for Verifying the exact environment that will run on HuggingFace Spaces before pushing to main, or testing Postgres connectivity without touching your local SQLite fallback.**

## Option 3 -- Hybrid: Train a Custom Model, Then Serve It

> `EfficientNet-B3 / ResNet-50 / ViT`  ·  `Kaggle / iNaturalist data`  ·  `GPU recommended`

> **Already-trained weights exist -- if you just want fine-tuned inference on the 13 North American species, download the model-v1 release (see Two Operating Modes) and skip this option entirely. Train only to change species coverage or push accuracy further.**

### Full pipeline
### Obtain labeled images
One folder per species: data/raw/<species_name>/*.jpg. Two data source options below.
### Option A: download a public Kaggle dataset

> **python research/scripts/download_data.py download crowww/a-large-scale-fish-dataset python research/scripts/download_data.py organize data/kaggle_tmp --output data/raw**

### Option B: download North American freshwater species from iNaturalist

> **make download-na-freshwater**

### Configure hyperparameters
All settings live in configs/training.yaml -- model architecture (EfficientNet-B3, ResNet-50, or ViT), epochs, learning rate, batch size.
### Train
Saves checkpoints/best.pt and classes.json on each improvement.

> **make train**

### Resume an interrupted run

> **make resume**

### Evaluate
Prints a per-class report and saves a confusion matrix.

> **make eval          # outputs/confusion_matrix.png**

### Export for edge / mobile (optional)

> **python -c "from services.fish_ai.predictors.efficientnet import FishPredictor; \ FishPredictor('checkpoints/best.pt').export_onnx()"**

### Serve the fine-tuned model
Once checkpoints/best.pt exists, the app switches to fine-tuned mode automatically on next restart.

> **make app make api**

> **Connecting to the shared AI service Once a checkpoint is trained here, omyfish-ai (the standalone shared microservice) mounts checkpoints/best.pt and data/metadata/fish_info.json as read-only volumes from this repo, so omyfish-java and omyfish-dotnet get the same fine-tuned predictions.**

| Advantages ✓  Full control over species coverage and training data ✓  Same predictor code path used by omyfish-ai once trained ✓  ONNX export available for edge/mobile deployment ✓  Two free dataset sources built in (Kaggle, iNaturalist) | Drawbacks ✗  Requires GPU for reasonable training time ✗  Manual labeling needed for species outside the two built-in datasets ✗  Largest time investment of the three options |
| --- | --- |

> **Best for Improving model accuracy beyond zero-shot CLIP, adding new species coverage, or producing the checkpoint that powers the shared omyfish-ai microservice for all enterprise stacks.**

## Persistent Storage (Supabase)
Set the DATABASE_URL environment variable (or HuggingFace Space secret) to a PostgreSQL connection string. Use the Connection Pooler -> Session mode (port 5432) URL for hosted environments like HF Spaces that lack IPv6 outbound access. The app falls back to SQLite when no DATABASE_URL is set.

## Deploy to HuggingFace Spaces
### Create a Space
SDK: Docker, name: omyfish
### Generate a write token
huggingface.co/settings/tokens
### Add it as a GitHub secret
Name it HF_TOKEN in repo Settings -> Secrets
### Push to main
The GitHub Actions workflow deploys automatically.

> **git push origin main**

Live demo: huggingface.co/spaces/fenghebonjour/omyfish

> **Timing tab on the Space The Space image bundles omyfish-ai (the bite-score service) from GitHub main at build time -- there is no separate AI Space. Pushing to this repo redeploys the Space and re-downloads omyfish-ai, so a rebuild here is also how bite-engine changes reach the deployed Timing tab.**

## Project Structure

| Path | Contents |
| --- | --- |
| apps/omyfish_api/ | FastAPI backend -- modular routers (routes/: auth, users, species, observations, health), repositories/ data layer, auth.py (bcrypt + JWT) |
| apps/omyfish_web/ | Streamlit web UI -- Timing · Identify · Map tabs + login/register with per-browser cookie sessions; timing.py renders the Bite Score forecast fetched from omyfish-ai |
| services/fish_ai/model/ | EfficientNet-B3 / ResNet-50 / ViT classifier definitions |
| services/fish_ai/predictors/ | Inference wrappers -- fine-tuned + CLIP zero-shot |
| services/fish_ai/training/ | Training loop, dataset, augmentations, evaluation |
| services/gis_service/ | EXIF GPS extraction, GeoJSON builder |
| shared/ | Schemas, config, events |
| data/raw/<species>/ | Training images, one folder per species |
| data/metadata/fish_info.json | 39-species knowledge base |
| configs/training.yaml | All training hyperparameters |
| checkpoints/ | best.pt + classes.json (required for fine-tuned inference; fetch via gh release download model-v1) |
| research/scripts/ | Dataset download helpers (Kaggle, iNaturalist) |
| tests/ | pytest suite (36 tests, unit + integration) -- run with make test; CI runs it on a schedule |

### Species knowledge base
data/metadata/fish_info.json contains profiles for 39 species. Each entry includes scientific name, habitat, diet, max size, conservation status, description, and a fun fact. Add entries here to enrich the identification cards shown in the UI.