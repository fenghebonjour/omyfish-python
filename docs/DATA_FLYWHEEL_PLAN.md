# Data Flywheel: Turning User Uploads into Better Models

## Short answer

Yes — every photo a user identifies is a potential training example, but today none of them are kept. This is a plan to close that loop safely: capture → label → curate → retrain → evaluate → promote, with a human checkpoint before anything touches the production model.

## Current state (verified in code)

- `shared/schemas/observation.py` and the `observations` table already have an `image_url` column, and `apps/omyfish_api/db/engine.py` / `001_initial_schema.py` persist it — but nothing in `apps/omyfish_api/routes/species.py::identify_fish` ever writes to it. **Uploaded images are decoded in memory for inference and then discarded.** Only the prediction (species, confidence, GPS) is saved.
- There is no object storage wired up anywhere (no S3/MinIO client in `requirements.txt` or infra) — a prerequisite for keeping the images at all.
- There's no correction mechanism: a user can save an observation, but there's no way for them to tell the app "that's wrong, it's actually a smallmouth bass," so no explicit label ever gets attached to an upload.
- `training.dataset.FishDataset` only reads from `data/raw/<class>/` folders — there's no ingestion path from the `observations` table into a training set.
- `checkpoints/last.pt` + `--resume` (used in the last training run) proves warm-starting already works — a retrain doesn't have to start from scratch.

So the flywheel doesn't exist yet — the DB schema is the only piece already in place.

## Why this matters

More users -> more geographic and lighting diversity than any single Kaggle/iNaturalist pull, and it's diversity in exactly the conditions the app is used in (real anglers, real phones, real water). But raw crowd uploads are also the easiest way to quietly poison a classifier if there's no gate before they enter training data — so the plan below treats "collect" and "trust" as separate steps.

## Phase 1 — Capture (consent + storage)

- Add an object store (MinIO locally / S3 in prod — matches the "shared infra" pattern already used for Postgres/PostGIS in `infrastructure/docker/docker-compose.yml`).
- On `/identify-fish`, when `save=True`, actually upload the image and populate `image_url` (today it's a dead column).
- Add an explicit opt-in flag at upload time — "use my photos to improve identification." Default off. Without this, stored images are just user data with no lawful basis for reuse in training. Needs a line in a privacy policy (see the App Store plan — there isn't one yet).
- Strip identifying EXIF beyond what's needed; keep GPS only if the user already opted into map display.

## Phase 2 — Labeling (the actual valuable signal)

- High-confidence accepted predictions are a *weak* signal at best — a saved observation doesn't mean the species was right, just that the user didn't bother to correct it.
- Add a lightweight confirm/correct step in the Identify tab: "Is this a {species}? Yes / No — pick the right one from top-3 / something else." Store as `confirmed_species` + `user_corrected: bool` on the observation.
- This is the one net-new piece of product surface required — everything else is backend.

## Phase 3 — Curation (don't trust the crowd blindly)

- Route corrected/low-confidence submissions into an admin moderation queue (there's already an admin dashboard and `require_admin` dependency in `apps/omyfish_api/routes/admin.py` — this is an additive endpoint, not new infra).
- Auto-reject anything the CLIP fish-gate already flagged as "not a fish" — never let those reach the queue.
- Only approved, moderator-confirmed images get copied into a versioned training folder, e.g. `data/user_contributed/<YYYY-MM>/<species>/`, keeping `user_id`/`timestamp` provenance so a contribution can be pulled back out (right-to-erasure) without re-deriving which file it was.

## Phase 4 — Automated retraining

- Trigger condition: N new approved images accumulated (e.g. 300–500) or a species falls below a minimum-sample threshold — not a fixed calendar schedule, since crowd volume is uneven per species.
- Retrain via warm-start from `checkpoints/best.pt` using the existing `--resume` path (`make resume`) rather than from scratch — cheaper and already proven to work.
- Keep a **fixed golden validation set** that user-contributed data never enters. This is the control group — without it, a model can "improve" on a validation split that's itself contaminated with the same crowd noise it's learning from.

## Phase 5 — Evaluation gate + rollout

- `make eval` against the golden set must show accuracy ≥ current `best.pt` (within a small tolerance) before a new checkpoint is allowed to replace it. Otherwise reject and keep the old one — never auto-promote on a regression.
- Version checkpoints (`best-v{n}.pt`) instead of overwriting; keep the last 2–3 for rollback.
- Optional: shadow-score the new model against live traffic (log both models' predictions, serve only the old one) for a few days before cutover, rather than an instant swap.

## What to build first

1. Object storage + actually wiring up `image_url` (Phase 1) — everything downstream depends on this existing.
2. The confirm/correct UI control (Phase 2) — without it there's no ground truth, just accepted guesses.
3. Moderation queue (Phase 3) — smallest addition, reuses existing admin auth.
4. Retrain trigger + golden-set gate (Phase 4–5) — automate only once 1–3 have run manually a few times and the data looks clean.
