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

---

## [~] B — Weakness audit follow-up (ported from omyfish-dotnet)

**Status:** IN PROGRESS (added 2026-09-11). `omyfish-dotnet` went through a
senior-dev-style weakness audit (its `BACKLOG.md` item F) and asked for the
same treatment across the rest of the family — already ported to
`omyfish-java`, `omyfish-python-web`, and `omyfish-ai`. Full explanation in
`docs/WEAKNESS_AUDIT.md` — this entry is the "what shipped". This repo is
the odd one out architecturally: the deployed Hugging Face Space runs
**Streamlit only** (plus a loopback-only bundled bite-score API) — the
FastAPI app under `apps/omyfish_api/` (auth, billing, admin, `/predict`,
`/identify-fish`, `/observations`) is a fully-built, fully-tested, legacy
multi-tenant API surface that is **never started in the deployed Docker
image**. That fact reshapes the practical risk of several findings below.

**Security:**
- ~~No rate limiting on the actually-reachable identify path~~ — fixed: a
  per-session cooldown (`_identify_rate_limited()` in
  `apps/omyfish_web/main.py`, 10 new identifications/60s/browser session)
  on Streamlit's Identify tab, since there's no ASGI middleware layer to
  hang a per-IP limiter on like the enterprise siblings' gateways. The
  FastAPI routes themselves still have no rate limiting — not reachable on
  the public Space today, but real if `apps.omyfish_api` is ever deployed
  reachably (see bonus finding 1 below). (§1.2)
- ~~Container runs as root~~ — fixed: non-root `USER app` with its own
  home (`/home/app`), not `/app` itself. A first attempt chowned the whole
  `/app` tree (needed for Streamlit's one-time
  `~/.streamlit/credentials.toml` write) but measured at 12+ minutes on a
  real build — real risk of the Hugging Face Space build timeout, for no
  benefit `COPY` doesn't already give a non-owner reader. Rebuilt scoped to
  `/home/app` ($HOME/$HF_HOME) plus the one real write path, `/app/data`
  (SQLite). Verified via `docker run --entrypoint id` (non-root) and a live
  `ensure_db()` call inside the built image. (§1.4)
- §1.1 (gateway auth) / §1.3 (refresh token) — not applicable as literally
  stated; §1.3 has a related, smaller-blast-radius exposure (a JS-writable
  cookie holding the single 24h access token) that's architecturally
  unfixable without a server-side proxy — noted, not fixed.
- ~~`GET /observations` leaked every user's data to anonymous callers~~ —
  fixed: now requires auth and scopes to the caller, matching the family
  convention (only `/observations/geojson` stays intentionally public).
  Updated the test that had locked in the old behavior, plus three others
  that used anonymous `GET /observations` for verification. (Bonus finding 2)

**Resilience:**
- ~~No global exception handling~~ — fixed:
  `@app.exception_handler(Exception)` in `apps/omyfish_api/main.py`. (§2.2)
- §2.1 (timeout/retry) — already fine on timeouts (every outbound call in
  this repo's own code already sets one); retry not fixed, lower urgency
  than `omyfish-ai`'s per-call-billed Groq client.
- §2.3/§2.4 (outbox/idempotency) — not applicable, no broker exists.

**Data layer:**
- ~~`ensure_db()` silently swallowed migration failures~~ — fixed: removed
  the bare `except Exception: pass`, now logs at error level before
  returning `False`. Deliberately not re-raised — this function is called
  from many places, including Streamlit script runs that don't expect it
  to throw — so every caller keeps its existing behavior on failure, but a
  real failure is now discoverable in logs instead of retried silently
  forever on every request. (§3.1)
- §3.2/§3.3/§3.4 — already fine or not applicable (Alembic's revision
  chain can't silently omit a file; the PostGIS `geom` column is actually
  populated, the opposite of dotnet's dead-column finding; no N+1 queries
  found anywhere).

**Testing/CI:**
- ~~CI's syntax-check step silently omitted the auth/billing/admin
  files~~ — fixed: `apps/omyfish_api/{auth,billing}.py` and
  `routes/{auth,users,billing,admin}.py` added to the `py_compile` list.
- Auth/billing/admin test coverage was already substantial before this
  audit — ahead of the other siblings' pre-fix baseline.
- **Not done:** the PostGIS/Alembic code path has zero test coverage
  (`conftest.py` always rebinds to a temp SQLite engine); no dependency
  scanning/lint/Docker-build check in CI; `deploy.yml`'s relationship to
  `ci.yml` passing isn't visible from the repo alone.

**Cleanup:**
- ~~`apps/omyfish_admin/` was an empty, zero-reference package~~ — deleted.
- ~~`CLAUDE.md`'s repository-structure section was stale~~ — fixed:
  corrected the `main.py`/`shared/` descriptions, and called out the
  in-process-vs-HTTP architecture split explicitly.

**Not done in this pass, left for a follow-up round** (see
`docs/WEAKNESS_AUDIT.md` for full detail):
- An explicit decision on `apps/omyfish_api`'s dead-code-on-Space status
  (bonus finding 1) — a product/ownership call, not a code fix.
- Retry on `apps/omyfish_web`'s outbound HTTP calls.
- Rate limiting on the FastAPI routes themselves.
- `JWT_SECRET` fail-closed enforcement in production config (bonus finding 3).
- Test coverage for the PostGIS/Alembic path; CI hardening (lint,
  dependency scan, Docker build check).
