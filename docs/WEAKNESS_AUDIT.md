# OMyFish Python — Weakness Audit (learning notes)

Ported from `omyfish-dotnet/docs/WEAKNESS_AUDIT.md`'s senior-dev-style review
(2026-09-10) — see that file for the original writeup, and
`omyfish-java`/`omyfish-python-web`/`omyfish-ai`'s own `docs/WEAKNESS_AUDIT.md`
for how this translation was already done three times for the rest of the
family. Tracked for real work in `BACKLOG.md` — this file is the "why".

**Central architecture finding, load-bearing for almost every entry below:**
`Dockerfile`'s `CMD` starts exactly two processes on the deployed Hugging
Face Space — the bundled `omyfish-ai` copy's `uvicorn` bound to
`127.0.0.1:8000` (loopback only) and `streamlit run apps/omyfish_web/main.py`
on `0.0.0.0:7860` (the actual public entrypoint). There is no
`uvicorn apps.omyfish_api.main:app` anywhere in the image's `CMD`.
Streamlit's own UI code imports `apps.omyfish_api`'s auth/billing/
repositories and calls them as **in-process Python functions**, never over
HTTP — so `apps/omyfish_api/routes/*.py` (the real FastAPI route handlers,
with their `Depends(...)` auth checks) are **not reachable on the public
Space at all**. They're fully exercised by `make api`/`docker-compose.yml`
(a real Postgres+API stack for local dev) and by the test suite, just not
by what `huggingface.co/spaces/fenghebonjour/omyfish` actually runs. This
reshapes the practical risk of the FastAPI-route findings below without
changing whether they're real bugs worth fixing.

---

## 1. Security

**Status: §1.4, plus the observations-leak and CI bonus findings, fixed
2026-09-11. §1.2's Streamlit-reachable half fixed; §1.1/§1.3 not
applicable as literally stated (see each entry).**

### §1.1 — Gateway auth enforcement — not applicable

No gateway exists here — this repo's FastAPI app is default-*allow* per
route, each endpoint opts into `Depends(get_current_user)`/
`Depends(require_admin)` individually. This is architecturally the
opposite of dotnet's bug (a second layer silently disagreeing with the
first) — there's no second layer to disagree. Verified the routes that
should require auth do (`routes/users.py`, `routes/admin.py` at the
router level, `routes/billing.py`'s `/me` and `/checkout` but correctly
not `/webhook`).

### §1.2 — No rate limiting on `/predict`/`/identify-fish` — present, fixed on the reachable path

**Problem:** the FastAPI routes have no rate limiting — but per the
architecture finding above, they aren't reachable on the public Space at
all. The actually-reachable equivalent is Streamlit's own Identify tab:
`ai_service.predict()` runs in-process on every file upload with zero
throttling — any visitor can drive unbounded local model inference (CPU-
bound EfficientNet/CLIP forward passes) just by reloading the page.

**Fix:** a per-session cooldown in `apps/omyfish_web/main.py`
(`_identify_rate_limited()`) — 10 new (non-cached) identifications per
60s per browser session, tracked in `st.session_state`. Streamlit has no
ASGI middleware layer to hang a per-IP limiter on like the enterprise
siblings' gateways, so this is the mechanism available without a
reverse-proxy/CDN layer in front of the Space — a visitor can still open
multiple sessions to bypass it, but this stops the common case (reloading/
re-uploading in one tab).

**Not fixed:** the FastAPI routes themselves (`POST /predict`,
`POST /identify-fish`) still have no rate limiting — real if `apps.omyfish_api`
is ever deployed reachably (see bonus finding 1). The bundled bite-score
service is lower-risk already (bound to `127.0.0.1:8000`, not reachable
from the internet directly).

### §1.3 — Refresh token in `localStorage` — not applicable as stated; related exposure noted, not fixed

**Not applicable in the literal sense** — there is no refresh token
anywhere in this system (`Token` has only `access_token`, no
`/auth/refresh` route exists, `jwt_expire_minutes` defaults to 24h single
access token). Architecturally different from the shared-frontend bug the
other three repos fixed, not a version of it.

**Related, smaller-blast-radius issue, not fixed in this pass:** the
access token is written into a script-set cookie
(`document.cookie = 'omyfish_token=...'` via `streamlit_js_eval`) — not
`localStorage`, but equally readable/writable by any JS on the page, since
a script can never set `HttpOnly` (only a server `Set-Cookie` response
header can, and nothing here sends one). Same XSS-exposure *class*, capped
at a 24h single token instead of a 30-day refresh token. A true `HttpOnly`
fix isn't available to a pure-Streamlit frontend without a server-side
proxy setting the cookie — left as a known limitation, not fixed here.

### §1.4 — Container runs as root — present, fixed

**Problem:** no `USER` directive anywhere in `Dockerfile`.

**Fix:** non-root `USER app`, with a dedicated home directory
(`/home/app`, via `useradd -m`) rather than making `/app` itself the new
user's home. First attempt chowned the whole `/app` tree instead (needed
since Streamlit writes a one-time `~/.streamlit/credentials.toml` on first
launch even in `--headless` mode, so `$HOME` has to be writable) — measured
at **12+ minutes** on a real `docker build` of this image alone, a real
risk of blowing the Hugging Face Space build timeout on top of the
Dockerfile's already-documented torch-wheel-size concern, for no actual
benefit (`COPY` leaves regular files world-readable by default, so a
non-owner user can already read everything under `/app` it needs to).
Rebuilt scoped to `/home/app` (`$HOME`/`$HF_HOME` point there — covers both
Streamlit's credentials file and the CLIP fish-gate's model cache) plus the
one real app-specific write path, `/app/data` (SQLite,
`apps/omyfish_api/db/engine.py`) — verified via `docker run --entrypoint id`
(non-root confirmed) and a live `ensure_db()` call inside the built image
(SQLite table creation succeeds as the new user). Local `docker build` wall
time stayed high regardless of scope (this WSL2/Docker Desktop environment
appears to be I/O-bound on image-layer export/unpack independent of the
actual bytes changed — not necessarily representative of Hugging Face's own
build infrastructure) but the *reason* for the original 12-minute cost
(recursively chowning the entire multi-GB dependency tree) is gone either
way.

---

## 2. Resilience

**Status: §2.2 fixed. §2.1 already fine (every outbound call in this
repo's own code already sets a timeout). §2.3/§2.4 not applicable.**

### §2.1 — No timeout/retry/circuit breaker — already fine (timeouts); retry not fixed

Every outbound `requests` call in this repo already sets an explicit
timeout — `apps/omyfish_api/routes/species.py`'s regs enrichment (5s,
wrapped in `try/except: pass`, best-effort by design), and all of
`apps/omyfish_web/regs_client.py` and `timing.py` (10-15s each). Unlike
dotnet's original bug, no *unbounded* HTTP call exists anywhere. No retry
exists (same minor gap `omyfish-python-web` fixed with a `Session` +
`urllib3.util.Retry`) — **not fixed in this pass**, lower urgency since
nothing here is billed per-call the way omyfish-ai's Groq client is.

### §2.2 — No global exception handling — present, fixed

**Problem:** no `@app.exception_handler` in `apps/omyfish_api/main.py` —
an unhandled exception produced FastAPI's raw default 500. Real for
anyone running the local/self-hosted API service, not the public Space.

**Fix:** `@app.exception_handler(Exception)` in `main.py` — logs and
returns a structured `{"error": "..."}` 500. Doesn't intercept
`HTTPException` — Starlette resolves that via its own more-specific,
already-registered handler first, so no special-case passthrough was
needed here (unlike `omyfish-java`'s Spring equivalent).

Streamlit's own error surface is separately, informally handled already:
risky UI sections are wrapped in `try/except Exception as e: st.error(...)`
ad hoc per-block — not centralized, but a predictor crash or DB error on
the actually-live surface already shows a friendly error, not a raw
traceback.

### §2.3 / §2.4 — Outbox pattern / consumer idempotency — not applicable

No message broker anywhere (confirmed by grep). `shared/events.py`'s
`emit()` is a docstring-honest no-op (`"""Log a domain event. Future:
publish to message queue."""` + a log line) — there's no publish step to
be non-atomic with the DB write, so the risk dotnet's outbox protects
against doesn't exist here.

---

## 3. Data layer

**Status: §3.1 fixed (the silent-swallow half). §3.2/§3.3/§3.4 already
fine or not applicable.**

### §3.1 — Schema-drift / auto-schema masking — present, fixed (the discoverability half)

**Problem, three-part finding:**
1. A real migration system (Alembic) exists for the PostGIS path —
   this is *not* dotnet's "auto-schema is the only mechanism" situation.
   `run_migrations()` calls `command.upgrade(alembic_cfg, "head")`, the
   correct idiomatic call, and Alembic's `down_revision` chain is
   drift-proof by construction (no hand-maintained file list to fall out
   of sync).
2. **But `ensure_db()` swallowed migration failures with a bare
   `except Exception: pass`** — a failed Alembic migration (bad SQL, lock
   timeout, connectivity blip) was caught silently, logged nothing, and
   the app started successfully against a database that might not have
   the expected schema. Every subsequent request retried the full Alembic
   upgrade per-request, masking the failure while doing repeated wasted
   work.
3. The SQLite path (the actual default — `DATABASE_URL` is unset unless
   explicitly configured) has no migration tool at all, just a DDL shim
   (`CREATE TABLE IF NOT EXISTS`) — this *is* dotnet's exact pattern.
   Whether the deployed Space actually uses Postgres+Alembic or the
   SQLite shim is an HF-secrets question outside this repo — worth the
   team confirming, since the two paths have materially different data
   durability.

**Fix:** removed the bare `except Exception: pass`; now logs the
exception at error level via `logger.exception(...)` before returning
`False`. Deliberately *not* re-raised — `ensure_db()` is called from many
places, including Streamlit script runs that don't expect it to throw —
so every existing caller keeps getting a clean `False` instead of a new
crash surface, while a real failure is now discoverable in logs instead
of silently retried forever.

### §3.2 — Incomplete migration runner — not applicable

Alembic auto-discovers every revision via its `down_revision` chain —
no dotnet-style external file list that could omit an entry.

### §3.3 — Dead PostGIS geometry column — not applicable, already correct

The opposite of dotnet's finding: `observation_repository.py` populates
`geom` on every insert (`ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)`), and
the matching GIST index is created and live.

### §3.4 — N+1 query — already fine

No per-row follow-up queries found anywhere (observation listing, species
metadata lookup, identify-fish flow) — species metadata is an in-memory
dict loaded once at construction, not a table.

---

## 4. Testing/CI

**Status: CI's syntax-check file list fixed. Everything else already
ahead of the other siblings' pre-fix baseline, or left open.**

Auth/billing/admin already had substantial test coverage before this
audit — `tests/unit/test_auth.py`, `tests/integration/test_api.py` (230
lines: register/login/me, 422 validation, 401/403 admin gating,
observations, `/predict`/`/identify-fish` including oversized-upload 413
and regs-down graceful degradation), `tests/integration/test_billing_admin.py`
(166 lines). Materially more than `omyfish-python-web` had *before* its
own audit-driven test-writing pass.

**Fixed:** `.github/workflows/ci.yml`'s "Check syntax" `py_compile` step
silently omitted `apps/omyfish_api/auth.py`, `billing.py`,
`routes/{auth,users,billing,admin}.py` — a pure syntax error in any of
them would pass this step (though `pytest` would still catch it via
`main.py`'s router imports, so this was narrower than dotnet's "zero
tests" finding — a stale/incomplete file list, same shape as dotnet's own
§3.2). Now includes all of them.

**Not fixed, left open:**
- The PostGIS/Alembic code path has zero test coverage — `conftest.py`'s
  `client` fixture always rebinds to a temp-file SQLite engine, so
  `run_migrations()`, the `geom`/GIST-index insert path, and the
  exception-logging fix above are all structurally untested against a
  real Postgres.
- No dependency/security scanning, no lint/format check, no Docker image
  build check in CI (same gap as every sibling).
- `.github/workflows/deploy.yml` uploads to the HF Space unconditionally
  on push to `main`, with no visible gate on `ci.yml` passing first
  (branch-protection settings, if any, aren't in-repo).

---

## Cleanup

- ~~`apps/omyfish_admin/` was an empty package~~ (`__init__.py` only, 0
  lines, zero references anywhere) — deleted. Same "confirmed dead,
  zero-reference, matches the precedent dotnet's own audit set for its
  stray scaffold directories" reasoning.
- `CLAUDE.md`'s repository-structure section was stale relative to the
  actual code: it described `apps/omyfish_api/main.py` as holding "All
  API routes (monolithic for now — splits in Phase 5)" — that split
  already happened (`routes/` has 7 files; `main.py` is just router
  wiring, 34 lines). It also described `shared/` as "Future: domain
  models, schemas, constants, utils" despite it already holding live,
  load-bearing code. Both corrected, and the CLAUDE.md structure section
  now calls out the in-process-vs-HTTP architecture split explicitly.
- No Helm/K8s placeholder-template issue exists (single Docker Space, no
  orchestration manifests).

---

## Bonus findings (not on the dotnet list, specific to this repo)

1. **The entire legacy auth/billing/admin API is dead code on the public
   HF Space, but fully live and Stripe-wired for local/self-hosted
   deployments.** This is a real ambiguity worth an explicit decision —
   delete it, document it as local-dev-only reference, or commit to
   actually wiring `docker-compose.yml`'s `api` service into a real
   second deployment. **Not decided or acted on in this pass** — this is
   a product/ownership call, not a code fix; flagging it here rather than
   picking an answer unilaterally.

2. **`GET /observations`/`GET /observations/geojson` leaked every user's
   data to anonymous callers by design, locked in by a passing test.**
   `list_observations` only filtered by `user_id` when a valid JWT was
   presented; an anonymous call fell through to the *unfiltered* branch —
   confirmed intentional by `test_authenticated_observation_gets_user_id`'s
   own assertion that an anonymous `GET /observations` returned both an
   authenticated and an anonymous user's rows. **Fixed**: `GET /observations`
   now requires auth and always scopes to the caller, matching the family
   convention (dotnet/java/python-web all require auth on the bare listing
   endpoint; only `/observations/geojson` is an intentionally public map
   feed, and stays that way here too, unchanged). Updated the test that
   locked in the old behavior plus three others that relied on anonymous
   `GET /observations` for verification (switched to the still-public
   `/observations/geojson` where the flow being tested was itself
   anonymous, and to an authenticated create+list where it wasn't).

3. **`JWT_SECRET` defaults to a per-process random value
   (`secrets.token_hex(32)`), not a hardcoded dev string** — safer than
   `omyfish-python-web`'s hardcoded-fallback bonus finding, but has its
   own footgun: every container restart invalidates every issued token,
   and multi-worker (`uvicorn --workers N`) deployment would give each
   worker a different secret, so a token from worker A fails to decode on
   worker B. **Not fixed in this pass** — worth requiring `JWT_SECRET` to
   be set (fail closed) in any real production config.

4. **CORS is open by default, self-documented, confirmed still true.**
   `allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(",")` —
   `CLAUDE.md` already said this ("restrict in production"); included
   only to confirm the code still matches the doc's claim. Not a new
   finding, not fixed (matches the documented, accepted tradeoff).

---

## Not done in this pass, left for a follow-up round

- A real decision on `apps/omyfish_api`'s dead-code-on-Space status
  (bonus finding 1) — product/ownership call, not a code fix.
- Retry (not just timeout) on the `requests` calls in
  `apps/omyfish_web/regs_client.py`/`timing.py` (§2.1).
- Rate limiting on the FastAPI routes themselves (only the actually-
  reachable Streamlit path was fixed).
- `JWT_SECRET` fail-closed enforcement (bonus finding 3).
- Test coverage for the PostGIS/Alembic path.
- CI dependency/security scanning, lint/format, Docker build check;
  confirming `deploy.yml`'s relationship to `ci.yml` passing.
