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

## [x] C — Wire live Stripe billing on the public HF Space

**Status:** Done (2026-10-21). Step 1 (success-URL confirmation) shipped
2026-10-20. Step 2 (split deployment) deployed and verified end-to-end
2026-10-21 — a real test-mode checkout on the HF Space activated the
subscription via the real Stripe webhook delivered to Render (confirmed via
Stripe's automatic resend after two bugs below were fixed). This directly
resolves bonus finding 1 above (`apps/omyfish_api` is dead-code-on-Space) for
the billing slice specifically.

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

**Step 2 progress (2026-10-20):** platform picked — **Render free web
service**, accepting its sleep-after-15-min-idle/cold-start tradeoff (every
other card-free/no-sleep option checked — Koyeb, PythonAnywhere, Fly.io,
Railway — failed on at least one of the three asks; see chat for the
comparison). Scaffolded, not yet deployed:

- `render.yaml` (repo root) — Blueprint pointing at the existing
  `infrastructure/docker/Dockerfile.api` (already used by
  `docker-compose.yml` for local Postgres-backed dev, so this is the first
  time it runs anywhere outside that).
- `Dockerfile.api` — added the same CPU-only-torch pip step the root
  Dockerfile already uses (plain `pip install -r requirements.txt` would
  pull the ~6 GB CUDA wheels, which this service never needs — `/predict`
  is reachable here but nothing calls it — and would blow a free-tier
  build). Also switched `CMD` to shell form reading `${PORT:-8000}`, since
  Render's Docker runtime ignores `EXPOSE` and routes to whatever port the
  process binds, injecting its own `PORT` — the old hardcoded `--port 8000`
  would have left the service unreachable. Verified locally: built the
  image, ran it with `PORT=10000` (simulating Render), confirmed it bound
  to `0.0.0.0:10000` (not the old hardcoded 8000) and `GET /health`
  returned `{"status":"ok","db":true}`.

**Deployed:** `omyfish-api` on Render free plan (`render.yaml`), env vars set
per the checklist above (`DATABASE_URL` = shared Supabase, `JWT_SECRET` /
`ADMIN_EMAILS` matched to the main Space, `APP_BASE_URL` = the main Space's
direct `https://<user>-<space>.hf.space` URL — not the
`huggingface.co/spaces/...` wrapper page, since that one doesn't reliably
forward `?billing=success&session_id=...` query params down into the
Streamlit iframe). Webhook registered in Stripe's Workbench (the old
Developers → Webhooks menu is gone) against
`https://omyfish-api.onrender.com/billing/webhook` for
`checkout.session.completed`, `customer.subscription.updated`,
`customer.subscription.deleted`.

**Two production bugs found and fixed during first deploy (both pre-existing,
not introduced by the split — the HF Space was quietly hitting the same two
once this surfaced them):**

1. **`DATABASE_URL` driver mismatch.** Supabase's Connect-modal URI used the
   `postgresql+psycopg://` (psycopg3) scheme, but `requirements.txt` only
   installs `psycopg2-binary` — `engine.py`'s bare `create_engine(DATABASE_URL)`
   crashed with `ModuleNotFoundError: No module named 'psycopg'` on both
   Render and, once checked, the HF Space too (Streamlit imports the same
   `apps/omyfish_api/db/engine` in-process). Fixed by changing the scheme to
   `postgresql+psycopg2://` in both deployments' secrets — no code change
   needed.
2. **Stripe SDK object/dict mismatch.** `requirements.txt` pins
   `stripe>=9.0.0` unpinned; a newer SDK version returns `Event`/`Session`/
   `Subscription` objects that no longer support dict-style `.get()`/`[...]`
   access, which `billing.py` used throughout. Surfaced as a `500` on the
   live webhook (`AttributeError: 'get' is a dict method, but a Event is not
   a dict`) and a silently-swallowed failure in the `confirm_checkout_session`
   fallback (that `except Exception` block has no logging — worth adding if
   this path ever needs debugging again). Fixed with a small `_as_dict()`
   helper in `billing.py` that calls `.to_dict()` only when the object has
   it — real SDK objects get converted, the test suite's plain-dict stubs
   pass through unchanged.

Also hit along the way, not bugs: `STRIPE_PRICE_MONTHLY`/`STRIPE_PRICE_YEARLY`
were never set on the HF Space at all (pre-existing gap, unrelated to this
work) — set now on both deployments.

Step 1's `confirm_checkout_session` stays in place — harmless redundant path,
still covers the instant a checkout completes while Render's free tier is
asleep from idling.

## [x] D — Port omyfish-java's Omyshop (catalog/cart/checkout/orders/returns)

**Status:** Done (2026-10-21). omyfish-java has a full e-commerce module
(`services/shop-service`, "Omyshop"): product catalog, guest-or-account cart,
one-time Stripe checkout, orders, and a 30-day return/refund flow — entirely
separate from the subscription billing in item C above. Ported here
feature-equivalent, re-expressed in this repo's flat-module/raw-SQL
conventions instead of Java's hexagonal ports-and-adapters/gateway
architecture (no MinIO, no header-forwarded gateway auth — this is a single
FastAPI process with its own JWT + an optional-guest path).

Scope decisions made before building: guest+account cart parity (guest carts
merge into the account cart on login, same as Java), a static seed catalog
with no image-upload endpoint (Java itself has no create/update/delete-product
use case either, only a seeded catalog), and the full feature (catalog,
cart, checkout, orders, returns, admin order management) built in one pass
rather than phased.

**New**, mirroring `billing.py`'s existing patterns throughout (idempotency
keys, shared `WebhookEventRepository` dedup, the `_as_dict()`/`BillingNotConfigured`
helpers — extracted into `apps/omyfish_api/stripe_utils.py` so both modules
share it):
- `apps/omyfish_api/shop.py` — checkout orchestration (reserve stock + create
  a `pending_payment` order *before* the Stripe call, same ordering as Java's
  `ReserveOrderService`; a Stripe-call failure compensates by canceling the
  order and restocking, mirroring Java's `cancelAndRestock`), webhook
  handling (`checkout.session.completed`/`.expired`, own
  `STRIPE_SHOP_WEBHOOK_SECRET` — separate endpoint/secret from the
  subscription webhook), the synchronous success-URL confirmation fallback,
  and return-request/approve-refund.
- `apps/omyfish_api/repositories/{product,cart,order}_repository.py` — same
  raw-SQL-via-`text()` dict-row style as `subscription_repository.py`.
- `apps/omyfish_api/routes/shop.py` — a small `X-Cart-Token`/JWT owner
  resolver mirrors Java's `CartOwnerResolver` for external API clients (the
  Render deployment is a real HTTP service, not just Streamlit-in-process).
- `apps/omyfish_web/shop.py` + a new "Shop" tab in `main.py` — catalog, cart,
  checkout, order history with return requests, guest order lookup, and an
  admin order/return-approval section. A new `omyfish_guest_cart` cookie
  persists the guest cart token, same mechanism as the existing
  `omyfish_token` JWT cookie.
- Migration `006_add_shop_tables.py` (Postgres) + matching DDL in
  `engine.py::init_db()` (SQLite) for `shop_products/carts/cart_items/orders/
  order_lines`, plus a shared `shop_seed.py` catalog so both backends seed
  identically.
- `tests/integration/test_shop_*.py` — 18 new tests covering catalog, cart
  (including guest-merge-on-login), checkout (empty cart, insufficient
  stock, Stripe-failure compensation), webhook (paid/expired/dedup/invalid
  signature), and returns (within/past window, admin refund+restock). Full
  suite: 112 passed.

**A real bug found via Streamlit `AppTest` (not pytest)**: the guest-cart
cookie-token logic originally re-derived the token from `st.context.cookies`
on *every* rerun instead of once per session. Since `st.context.cookies` is
fixed from the initial request for the session's lifetime (same as the
existing comment on the auth-token cookie already notes), a cookie just
written via JS is never visible within that same session — so every widget
interaction would have minted a fresh random guest token and silently
orphaned the cart. Fixed by gating it on `"guest_cart_token" not in
st.session_state`, same guard shape as the existing `"auth_user" not in
st.session_state` check for the auth cookie. Caught by running the actual
Streamlit script headlessly via `streamlit.testing.v1.AppTest` (clicking
"Add to cart" across reruns) — worth reaching for `AppTest` again for any
future session-state-across-reruns logic, since pytest's API-level tests
can't see this class of bug at all.

**Follow-up required before relying on this for real money, mirroring item
C's own deploy checklist**: register a second Stripe webhook endpoint
(`https://omyfish-api.onrender.com/shop/webhook`, events
`checkout.session.completed`/`checkout.session.expired`) and set
`STRIPE_SHOP_WEBHOOK_SECRET` on both the HF Space and Render.

**Done (2026-10-22):** destination registered in Stripe Workbench (Stripe's
"Add endpoint" button is now called "Add destination"), secret set as an HF
**Secret** and a Render **Environment Variable** (same underlying env var
either way — the two platforms just split sensitive vs. plain config
differently: HF has separate Variables/Secrets tabs, Render has one list
with a per-entry secret toggle). Verified via Stripe Workbench's in-browser
Stripe Shell (`stripe trigger checkout.session.completed`), confirmed `200`
in the destination's Event deliveries log.

**Placeholder images fixed, then upgraded to real photos (2026-10-22):**
the original seeded `image_url`s were raw (non-base64) SVG data URIs — the
hex colors' `#` was parsed as the URL fragment delimiter, truncating the
SVG mid-attribute, so every product showed a broken-image icon. Fixed by
base64-encoding (migrations 007/008 backfill already-seeded rows). Then,
since `omyfish-java`'s own seed data never had real photos either (its `V4`
migration comment says so explicitly — real photos there only exist if an
admin uploads one via MinIO, not ported here), sourced 6 CC-licensed/
public-domain photos from Wikimedia Commons/Openverse for Spinnerbait Lure,
Worm Pack, Popper, Sunglasses, Tackle Box, and Fillet Knife — resized and
inlined the same self-contained way. Added `shop_products.image_credit` for
the CC BY/BY-SA attribution 5 of the photos require, shown as a caption
under the image in the Shop tab (migration 009).

**Last 2 placeholders replaced too (2026-10-22):** Braided Fishing Line and
the Insulated Mug had no good match in Openverse's Flickr-sourced results
(line searches mostly surfaced wildlife entangled in fishing line, not
product shots). Broadening to Openverse's CC0-only sources (Rawpixel) found
a fishing-reel photo with line visibly wound on the spool, and a steaming
enamel camp mug — both CC0. All 8 products now use real photos; no SVG
placeholders remain (migration 010 backfills Postgres; SQLite reconciles
on every `init_db()` call as before).
