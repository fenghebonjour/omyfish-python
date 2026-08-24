# OMyFish — Backlog

Deferred ideas and future work. Not committed scope — parking lot for things worth doing.

---

## [x] Add `omyfish-python-web` sibling repo (learning purpose)

**Status:** SCAFFOLDED (2026-07-28) at `../omyfish-python-web` — Django project, all 5 apps
(accounts/species/observations/notifications/billing), JWT auth, AI-service client, docker-compose,
frontend copied from omyfish-java, smoke-tested end to end (register/login, species list,
observations CRUD + geojson, notifications, billing/me, admin permission gating). Not yet committed
to git. Design spec below kept for reference.

**Goal:** Round out the enterprise-language family with a Python full-stack web framework, so the
same domain is expressed once per major backend ecosystem — for learning/comparison.

**Target family layout:**

| Repo | Role | Stack |
|---|---|---|
| `omyfish-python` (name unchanged) | ML/AI service that exposes a small API | FastAPI + Streamlit + PyTorch/timm — the AI origin, reused by all others over HTTP |
| `omyfish-python-web` (new) | Full-stack web app | Django + DRF + GeoDjango/PostGIS |
| `omyfish-java` | Enterprise scaffold | Java 21 · Spring Boot · Hexagonal |
| `omyfish-dotnet` | Enterprise scaffold | .NET 10 · ASP.NET Core · Clean Architecture / CQRS |

**Decisions:**
- **Name:** `omyfish-python-web` — language-neutral, consistent with `-java` / `-dotnet` naming
  (framework name kept out of the repo name).
- **No renames:** `omyfish-python` keeps its current name.

**Architecture (locked): idiomatic Django monolith + DRF apps** — NOT a 5-microservice mirror.
One Django project (`config/`), apps: `accounts`, `species`, `observations`, `notifications`,
`billing` (+admin). DRF exposes the exact frontend REST contract at ONE origin, so Django itself
replaces the Java/.NET api-gateway — no separate gateway/RabbitMQ needed.

**Frontend (locked): reuse the siblings' Next.js SPA verbatim.** It is fully decoupled — every call
goes through `NEXT_PUBLIC_API_URL` (default `http://localhost:8080`). Zero component changes; just
point that env var at Django. Consequence: Django is an **API backend (DRF)**, NOT server-rendered
templates (supersedes the earlier "server-rendered species pages" note). This aligns with the
"unify the frontend" todo — one SPA, swappable Java/.NET/Django backends.

**REST contract to implement** (all JSON **camelCase**, string UUID ids; JWT returns
`{token, refreshToken, userId, email, role}`):
- `POST /api/auth/register` · `POST /api/auth/login` · `POST /api/auth/refresh`
- `POST /api/v1/species/identify` (multipart `image`,`topK`) → `{predictions[], uncertain, imageKey, isFish}`
- `GET /api/v1/species/bite-score/today|forecast?lat&lon&species[&hours]`
- `GET /api/v1/species?northAmericanFreshwater=`
- `GET/POST /api/v1/observations`, `DELETE /api/v1/observations/{id}`, `GET /api/v1/observations/geojson`
- `GET /api/v1/notifications`, `PUT /api/v1/notifications/{id}/read`
- `GET /api/billing/me`, `POST /api/billing/checkout`
- `GET /api/admin/stats`, `GET /api/admin/subscriptions`, `POST /api/admin/subscriptions/{id}/{grant|revoke|extend-trial}`

**AI reuse:** consume the standalone AI service over HTTP (like `-java`/`-dotnet`), don't re-implement.
- `identify` → AI `POST /predict` `{image_base64, top_k}`; map snake_case→camelCase, `common_name`→`speciesName`.
- `bite-score/*` → AI `GET /bite-score/{today,forecast}`; response is same shape, just recursively camelCase the keys.

**Observations geo (pragmatic call):** scaffold stores `latitude`/`longitude` floats and builds the
GeoJSON `FeatureCollection` in the view → `make run` works instantly on SQLite, no GDAL/GEOS. Document
the GeoDjango `PointField` + PostGIS spatial-index upgrade diff in `ARCHITECTURE.md`. docker-compose
still ships PostGIS to mirror siblings.

**JWT:** `djangorestframework-simplejwt` wrapped in custom register/login/refresh views to emit the
exact `{token, refreshToken, userId, email, role}` shape. Custom `User` (email as username, `role` field).

**Also mirror sibling conventions:** `ARCHITECTURE.md` w/ diagrams + scaling table, `README.md`,
`CLAUDE.md`, `Makefile`, `docker-compose.yml`, `.env.example`, CI. Target path: `../omyfish-python-web`.
