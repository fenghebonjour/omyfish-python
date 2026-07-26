# Gap Analysis: OMyFish → Live App Store App

## Short answer

Far. Not because the AI/backend is weak — the FastAPI service, auth, billing, and admin layer are real — but because **there is currently no native (or native-wrapped) client at all**, and the one UI that exists (Streamlit) cannot legally or technically be the thing submitted to Apple. Production hosting today is a HuggingFace Spaces demo, not infrastructure that can back a paid iOS app. This is a rebuild-the-frontend-and-harden-the-backend project, not a packaging step.

## What's verified working today

- FastAPI backend (`apps/omyfish_api/`) with modular routers: auth (JWT + bcrypt), users, billing, admin, species/predict, observations. Real code, not a stub.
- Postgres/PostGIS persistence, Alembic migrations.
- Stripe subscriptions with webhook handling (`apps/omyfish_api/routes/billing.py`) and an admin dashboard to comp/revoke subscriptions.
- Trained model + inference path, CLIP fallback, EXIF GPS extraction.
- Test suite (~870 lines) and CI (`.github/workflows/ci.yml`).

## Blocking gaps

### 1. No native/mobile client
The only UI is Streamlit (`apps/omyfish_web/`) — a server-rendered Python web app. Apple's App Review Guideline 4.2 ("Minimum Functionality") rejects thin WebView wrappers around a website with no native capability. To actually ship, you need one of:
- A native Swift/SwiftUI app calling the existing FastAPI backend directly, or
- A cross-platform app (React Native / Flutter) calling the same backend, or
- A Capacitor-wrapped PWA *with* real native features added (camera, push notifications, offline handling) so it clears 4.2.

This is the single largest gap and effectively its own project.

### 2. Billing model conflicts with App Store rules
`billing.py` charges via Stripe Checkout directly. Apple requires **In-App Purchase (StoreKit)** for digital subscriptions consumed inside the app (Guideline 3.1.1) — you cannot link out to a Stripe checkout page from inside an iOS app for this kind of content. Practically this means adding a parallel StoreKit purchase flow with server-side receipt validation feeding the same `SubscriptionRepository`, and keeping Stripe only for the web version. Two billing systems to reconcile, not a config flag.

### 3. Hosting is a demo, not production infra
`.github/workflows/deploy.yml` deploys to a HuggingFace Space. That's fine for a portfolio demo; it is not a production backend for a real user base — no autoscaling, no SLA, uncertain uptime under sleep/cold-start behavior, and `docker-compose.yml`'s Postgres credentials (`omyfish`/`omyfish`) are dev defaults, not production secrets. Needs: a real host (Fly/Render/AWS/GCP), managed Postgres with backups, TLS, secrets management, and `ALLOWED_ORIGINS` locked down (currently defaults to `*`).

### 4. Account deletion is admin-only
`apps/omyfish_api/routes/users.py` — `DELETE /users/{user_id}` requires `require_admin`. Apple Guideline 5.1.1(v) requires apps that support account creation to let users **delete their own account from within the app**, not just request it from a human. Needs a self-service `DELETE /users/me` path.

### 5. No privacy policy or terms of service
Nothing in the repo (`privacy`, `terms` search comes up empty). Apple requires a privacy policy URL in App Store Connect, plus an accurate "App Privacy" nutrition-label declaration (camera, location, and any data shared with third parties like Stripe must be disclosed). This also blocks Phase-1 of the [[DATA_FLYWHEEL_PLAN]] — you can't reuse uploaded photos for training without a policy that says so.

### 6. No crash reporting / observability
No Sentry or equivalent anywhere in the actual app code (only present as a transitive dependency in the virtualenv, unused). Shipping to the App Store without crash visibility means the first sign of a broken release is bad reviews, not a dashboard.

### 7. No App Store Connect assets
No app icon set, screenshots, marketing description, age rating, or export-compliance declaration exist yet — normal for this stage, but real work (design + legal, not engineering).

## What's *not* a blocker

- The AI predictor, GIS/EXIF handling, and DB schema translate directly to a mobile client via the existing API — no rework needed there.
- Auth (JWT) is a reasonable foundation for a mobile client (though consider adding Sign in with Apple — required if you offer other third-party logins like Google/Facebook, per Guideline 4.8).
- Test coverage and CI already exist, which most projects at this stage don't have.

## Phased plan

**Phase 1 — Backend hardening (no client changes)**
- Move off HuggingFace Spaces to real hosting with managed Postgres, TLS, and locked-down `ALLOWED_ORIGINS`.
- Self-service account deletion endpoint.
- Wire up Sentry (or similar) for API error tracking.
- Draft privacy policy + ToS (blocks both App Store submission and the data-flywheel plan).

**Phase 2 — Native/mobile client**
- Pick React Native or native Swift (recommendation: React Native if a future Android release matters, since the backend is already platform-agnostic; native Swift if iOS-only and best-in-class camera/location UX matters more).
- Rebuild Identify, Map, and Timing tabs as native screens calling the existing FastAPI endpoints — the backend contract doesn't need to change.
- Add camera/location permission strings, push notifications (e.g. "great bite window starting now" from the Bite Score forecast), offline handling for spotty cell service near water.

**Phase 3 — StoreKit billing**
- Add In-App Purchase products mirroring the existing `billing.PLANS`.
- Server-side receipt validation feeding `SubscriptionRepository`, so the admin dashboard's comp/revoke tooling keeps working across both Stripe (web) and StoreKit (iOS) subscribers.

**Phase 4 — Submission prep**
- App Store Connect listing: icon, screenshots, description, age rating, App Privacy answers.
- TestFlight beta with real anglers before public submission — the Timing/Bite Score and species ID features need field validation beyond unit tests.
- Submit; budget for at least one rejection-and-resubmit cycle (common even for compliant apps).

## Bottom line

Backend: ~60% of the way there. Client + compliance + production infra: effectively 0% — those are the actual remaining project.
