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

---

## [ ] C — Wire live Stripe billing on the public HF Space

**Status:** Decided (2026-10-20), staged — see below. Step 1 (success-URL
confirmation) implemented 2026-10-20. Step 2 (split deployment) not started.
This directly resolves bonus finding 1 above (`apps/omyfish_api` is
dead-code-on-Space) for the billing slice specifically, by deciding whether
and how Stripe actually gets wired up there.

**Key reuse point:** the Stripe *secret key* can be shared across the whole
family — it's account/sandbox-scoped, not app-scoped. `omyfish-java`'s
`shop-service/application.yml` documents this exact pattern already
(`# Can reuse the same Stripe account's secret key`). Only the **webhook
signing secret** needs to be unique per registered endpoint URL, since
Stripe ties that secret to the specific endpoint in the Dashboard.

**The blocker found:** the root `Dockerfile`'s `CMD` only starts two
processes — the bundled ai-service on `127.0.0.1:8000` (loopback-only) and
Streamlit on the one exposed port, `7860`. `apps/omyfish_api`'s FastAPI app
(home of `/billing/webhook`) never runs in that container, so there is
currently no reachable URL for Stripe to deliver `checkout.session.completed`
(or any other) event to. Checkout session *creation* already works today
(Streamlit's `admin.py::subscription_sidebar` calls
`billing.create_checkout_session` in-process), but a real payment would
never flip the subscription to `active`. Separately, `billing.py`'s
`success_url=f"{settings.app_base_url}?billing=success"` redirect target is
already dead code too — nothing in `main.py`/`admin.py` reads
`st.query_params`, and the URL doesn't even carry a session id to look up.

**Options considered:**

- **A — in-container reverse proxy** (nginx/Caddy on 7860, routing
  `/billing/webhook` to a real FastAPI process, everything else to
  Streamlit). Gets the full async webhook path (renewals, Stripe-portal
  cancellations, disputes). Risks found specific to this container:
  no process supervisor today (`CMD` just backgrounds with `&`/`exec`, and
  a missing dep has already once caused the ai-service to "crash silently
  at import time" while Streamlit still came up looking healthy); Streamlit
  needs correct WebSocket-upgrade proxying or reruns silently break after
  first load; the HF Space's SQLite file would gain a second concurrent
  writer process (`database is locked` risk); `apps/omyfish_api`'s routes
  (incl. `/admin/*`) become internet-reachable for the first time; roughly
  doubles the process's RAM footprint on a likely free/basic-tier instance;
  one more thing that can blow the Space's already-tight build timeout.

- **B — synchronous success-URL confirmation.** Add
  `{CHECKOUT_SESSION_ID}` to the success_url template; have Streamlit read
  `st.query_params` on load, retrieve that Checkout Session from Stripe,
  and apply the same activation logic `checkout.session.completed` would
  have — directly, no webhook needed. Cheap, no new process, no proxy.
  Tradeoff: only covers the moment checkout completes; a later renewal
  failure or a Stripe-customer-portal cancellation never reaches the Space
  without a webhook — those still need the full path below.

- **Alternatives that keep the real webhook, instead of running it inside
  the fragile Streamlit container:**
  1. **Split `apps/omyfish_api` into its own deployment** (second HF Space,
     or Fly/Render free tier) pointed at a **shared external Postgres** —
     register the Stripe webhook against *that* URL. Zero changes to the
     existing Streamlit container; already-documented direction for this
     repo (`docs/OMyFish-Python-Startup-Strategies.md` names Supabase
     Postgres as the intended persistence story past SQLite), and the
     Alembic/Postgres path was already verified working end-to-end
     (2026-10-19, local Postgres container). Cost: a second deployment and
     DB to provision/manage, secrets duplicated across two deploys.
  2. **A minimal webhook-only serverless function** (Cloudflare
     Worker/Vercel function) that just verifies the Stripe signature and
     writes to that same shared Postgres, instead of running all of
     FastAPI. Lighter than #1, but means re-implementing signature
     verification and event-dispatch logic somewhere else — a second copy
     of `billing.py`'s dispatch logic that can drift.
  3. **Stripe CLI (`stripe listen --forward-to`)** — legitimate for local
     webhook testing, not a deployed-production answer (needs a
     forwarding process you keep running yourself).

**Decision (2026-10-20):** split-deployment (#1) is the real target, staged
in two steps instead of built all at once:

1. **Now, on the existing Space:** ship **B** (success-URL confirmation) as
   the interim activation path. It's cheap, needs no new process, and is
   already compatible with this session's idempotency work —
   `create_checkout_session` already takes `idempotency_key`, so replaying
   the same Checkout Session id on a page reload is already safe. Closes
   the "checkout works but the subscription never activates" gap today
   with zero new infrastructure.
2. **Before relying on it for real money:** stand up #1 — `apps/omyfish_api`
   as its own small deployment against the shared Supabase Postgres, with
   the Stripe webhook registered against *that* URL. It's the only option
   that gets real async events (renewals, portal cancellations, disputes)
   without touching the fragile single-container Space (rules out **A**:
   no process supervisor, SQLite second-writer risk, `/admin/*` going
   public, RAM/build-timeout pressure) and without re-implementing
   `billing.py`'s dispatch/idempotency/dedup logic in a second runtime
   (rules out **#2**: exactly the kind of drift-prone duplicate the
   idempotency/webhook-dedup/reconcile work this session was built to avoid
   having two copies of).

Run `reconcile()` on a schedule (e.g. hourly, `lookback_hours` at least 2x
the schedule interval) regardless of which step is live — it's the safety
net for whatever a missed webhook or a B-only window drops, and it's
already wired to repair exactly that gap.

**A** (in-container proxy) and **#3** (Stripe CLI) are out: A's risk list is
specific to this container and not worth it given a working two-step
alternative; #3 is dev-tooling only, not a production answer.
