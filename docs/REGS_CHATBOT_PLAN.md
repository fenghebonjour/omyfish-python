# Quebec Fishing-Regs Chatbot: Plan

## Short answer

Feasible, and it fits the existing shared-service pattern cleanly: a new `regs_advisor/` domain in `omyfish-ai` (sibling to `bite_prediction/`), exposed over HTTP, consumed by a new Streamlit tab for free-form Q&A **and** auto-invoked by the Identify tab right after a species prediction. Two genuinely different data problems are bundled in one feature — "legal to keep" (regulatory, zone-based) and "safe to eat" (contaminant advisory, already have a clean source) — plus a third, softer one (tackle/technique/skills) that has no authoritative government source and has to be curated by hand.

## Current state (verified in code)

- `apps/omyfish_api/routes/species.py::identify_fish` already accepts `latitude`/`longitude` as optional form fields and threads them into the saved observation — the hook point for auto-triggering regs lookups already exists, nothing new to add there.
- `apps/omyfish_web/timing.py` already has a working browser-geolocation pattern (`streamlit_js_eval.get_geolocation`, manual lat/lon override, `reverse_geocode` via a free API) — reusable as-is for the regs feature instead of building location capture twice.
- `../omyfish-ai/bite_prediction/` is the template to copy: `router.py` (FastAPI routes), `schemas.py` (Pydantic I/O), `engine/` (pure logic), `providers/` (external API clients). `apps/omyfish_web/timing.py` talks to it over HTTP via `BITE_SERVICE_URL`. The regs feature should follow the identical shape.
- `data/metadata/fish_info.json` is a flat list of 141 records keyed by `species` (habitat, diet, max size, conservation status, description, fun fact) — a natural place to *extend* with tackle/technique fields rather than invent a new species metadata file.
- Consumption-advisory data source is already confirmed (see [[quebec-fishing-regs-chatbot-idea]]): Données Québec publishes the "Guide de consommation du poisson" as direct CSV/GeoJSON/GPKG downloads plus a queryable Esri REST `MapServer`, keyed by species + size bracket + site/waterbody. No scraping needed.
- **Zone lookup and catch/possession limits are now both confirmed (Phase 0 complete, 2026-07-26)** — see the Phase 0 section below for the concrete endpoints. Neither is in Données Québec or MFFP's open-data catalog (checked and ruled out); both live on a separate official site, `peche.faune.gouv.qc.ca`, and are reachable as plain unauthenticated HTTP GET requests — no browser automation needed in production.

## Why this matters

Identify already tells the angler *what* fish they caught. Timing already tells them *when* to fish. Neither tells them whether they're allowed to keep it, or whether it's safe to eat — which is the actual point of catching a fish. Bundling that as an automatic, no-extra-tap addition to the Identify result (rather than a separate lookup the user has to remember to do) is the highest-value part of this feature; the general Q&A chatbot is valuable but secondary.

## Architecture

```
apps/omyfish_web/
  main.py           existing tabs: Timing · Identify · Map
  regs.py           NEW — "Regs & Tips" tab: free-form chat UI
  timing.py         (unchanged; geolocation helper reused, not duplicated)

apps/omyfish_api/
  routes/species.py identify_fish — after prediction, if lat/lon present,
                     calls omyfish-ai regs endpoints and folds the two
                     results into the response (mirrors how it already
                     folds in coords today)

../omyfish-ai/
  regs_advisor/                NEW — sibling to bite_prediction/
    router.py                  POST /regs/ask, GET /regs/limits, GET /regs/consumption
    schemas.py                 LimitsRequest/Response, ConsumptionRequest/Response, ChatRequest/Response
    engine/
      zones.py                 lat/lon -> zone_id (point-in-polygon)
      limits.py                species + zone_id -> daily/possession limit, season, min size
      consumption.py           species + size_cm? + lat/lon -> meals/month advisory
      retrieval.py             chunked KB + embedding similarity for free-form Q&A
    providers/
      consumption_client.py    wraps the Données Québec Esri REST / static export
    knowledge_base/            curated markdown: regs text, tackle/technique notes, season/behavior tips
```

This keeps `omyfish-ai` as the single canonical AI service (per `CLAUDE.md`), so the .NET and Java sibling projects get the regs chatbot for free the same way they already get Bite Score.

## Data sources, by question type

| Question type | Source | Status |
|---|---|---|
| "How many can I legally keep?" | `peche.faune.gouv.qc.ca/RegPec/en/Info/Reglements?id_zone={id}` — see Phase 0 | **Confirmed, ready to integrate** |
| "Is it safe to eat?" | Données Québec "Guide de consommation du poisson" (CSV/GeoJSON/Esri REST) | **Confirmed, ready to integrate** |
| "Which zone am I in?" | `ZonesPecheEn/MapServer/0` point-in-polygon query — see Phase 0 | **Confirmed, ready to integrate** |
| "When/where/what species/how" (general) | Curated knowledge base: quebec.ca regs text + hand-written tackle/technique/season notes | No authoritative single source for tackle/skills — this is editorial content, budget writing time, not scraping time |

## On LangChain

Recommend **skipping it for Phase 1–2**. The actual data flow is single-hop: user question → retrieve top-k chunks from a small curated corpus (regs text + tackle notes, likely well under a few hundred pages) → one LLM call with that context → answer. That's a `sentence-transformers` embedding + cosine similarity (numpy, no vector DB needed at this corpus size) — LangChain's orchestration value (multi-step chains, agents deciding which of several tools to call) isn't earning its keep yet.

Revisit LangChain (or native function-calling on whichever LLM is used) once/if the chatbot needs to *dynamically* decide mid-conversation which of several tools to invoke — e.g. "is a 40cm walleye I caught near Lac Saint-Jean legal, and can I eat it?" requires the model to call both `limits` and `consumption` with parsed species/size/location before answering. That's a small, fixed tool-use pattern (2–4 tools) — still solvable with direct function-calling, not a strong LangChain case even then. Flag this as a checkpoint, not a default.

## Phased plan

**Phase 0 — Data discovery — COMPLETE (2026-07-26)**

Neither the zone polygons nor the numeric limits are in Données Québec or MFFP's open-data file server (`diffusion.mffp.gouv.qc.ca`) — both were checked and ruled out. The real source is a separate official site, `peche.faune.gouv.qc.ca` ("Sport fishing in Québec — periods, limits and exceptions", run by MFFP), reached by tracing the `quebec.ca` limits page's "interactive map" link through its Geocortex Essentials config to the underlying public ArcGIS REST services.

- **Zone lookup (lat/lon → zone):** `GET https://peche.faune.gouv.qc.ca/arcgiswa/rest/services/PRODC-E/ZonesPecheEn/MapServer/0/query` — a standard Esri feature-layer point-in-polygon query, no auth. Example: `?geometry=-71.2080,46.8139&geometryType=esriGeometryPoint&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=ID_ZONE,NM_ENDRO_EN,VA_HYPRL_REGLE_EN&returnGeometry=false&f=json` for Quebec City returns `{"ID_ZONE": 2651, "NM_ENDRO_EN": "Zone 27", "VA_HYPRL_REGLE_EN": "https://www.quebec.ca/.../zone-27/"}`. Note: the `ID_ZONE` value in this layer (e.g. 2651) is *not* the same ID the limits search below expects (e.g. 31) — the two subsystems use different internal IDs. Match by the `NM_ENDRO_EN` zone-name string instead (see the static mapping below), not by ID.
- **Catch/possession/length limits (zone → species table):** `GET https://peche.faune.gouv.qc.ca/RegPec/en/Info/Reglements?id_zone={id}&resultats=True` returns a full server-rendered HTML page containing a structured table: species, catch limit, length limit, fishing device, notes — grouped by season period (e.g. "From May 15 to November 30 — Walleye and sauger — 6 in all — Walleye: 37cm to 53cm inclusively — Angling only"). Confirmed reachable via plain `curl`/`requests`, no session/cookies/JS required, no `id_saisn` (season) param needed — it defaults to the current season. `id_zone` is a fixed internal ID, not the display zone number; the full 34-entry name→id mapping (e.g. `{"Zone 27": 31, "Zone 19 north": 3063, "Zone 22 south": 25, ...}`) is embedded as a static JS array in the page HTML at `https://peche.faune.gouv.qc.ca/regpec/en/info/reglements` — small enough to hardcode as a lookup table (zone boundaries/names essentially never change) rather than re-fetch it per request.
- Discovery path (for reference, not something Phase 1 needs to repeat): `quebec.ca` limits page → link to `peche.faune.gouv.qc.ca/regpec/carteinteractive/en` (a Geocortex Essentials viewer, different framework than the Experience Builder app behind the consumption guide) → its `Desktop.json.js` config → `GeocortexREST/sites/PECHE` → captured actual network traffic (via headless Playwright, since Geocortex apps don't expose their layer list in static config) → found the underlying public Esri `arcgiswa/rest/services/PRODC-E/*` MapServer folder, which includes `ZonesPecheEn` (zone polygons) and `PlansEauExceptionsEn` (lake-specific rule exceptions, same pattern, not yet needed for Phase 1). The limits table itself was found separately via the "Fishing periods, limits and exceptions" link on the same quebec.ca page, which is a classic ASP.NET/DevExpress search form (`regpec/en/info/reglements`) — driving it once with Playwright revealed that its "Search" button just navigates to a plain GET URL with `id_zone` in the query string, so production code can skip the form entirely.
- No `robots.txt` on the domain; this is a normal public government page, not a hidden API — scrape politely (cache results, don't hammer it per-request) same as any other gov data source.
- Licensing/attribution on Données Québec exports (consumption dataset) still needs a quick check (typically CC-BY) before redistributing through the app — the one open item left in Phase 0, and low-risk.
- Exit criteria met: "(lat, lon) → zone → limit table" and "(species, size_cm, lat, lon) → nearest advisory site → meals/month" are both answerable without any hand-scraped one-off — both are live, queryable HTTP endpoints.

**Phase 1 — Structured backend, no chat UI yet**
- Build `regs_advisor/` in `omyfish-ai` per the module layout above: `zones.py`, `limits.py`, `consumption.py`, and `GET /regs/limits`, `GET /regs/consumption`.
- Wire `identify_fish` in `apps/omyfish_api/routes/species.py`: when lat/lon are present alongside a confident prediction, call both endpoints and add `legal_limit` and `consumption_advice` fields to the response (additive — doesn't change existing response shape for callers that don't send location).
- Streamlit Identify tab: render two small info cards under the existing species card — "Daily/possession limit: N (zone X)" and "Safe to eat: N meals/month" — only when the data is present, with a visible disclaimer + link back to the official source.
- Verify: unit tests for `zones.py`/`limits.py`/`consumption.py` against known fixture coordinates and species (mirrors the existing `bite_prediction` test structure); manual end-to-end check via `make api` + `make app` with a real photo + real coordinates.

**Phase 2 — Free-form Q&A ("Regs & Tips" tab)**
- Write the curated knowledge base: regs summary text (with source links, not verbatim legal copy), and tackle/technique/season notes — extend `fish_info.json` per-species where it's species-specific, keep general "how to fish for X technique" content as separate markdown.
- Build `retrieval.py`: chunk the KB, embed once at build/startup, cosine-similarity top-k at query time.
- `POST /regs/ask`: retrieved chunks + (if species/zone/location were parsed from the question) structured lookups from Phase 1 + user question → one LLM call → answer with a "verify with official sources" disclaimer on any regulatory claim.
- New `apps/omyfish_web/regs.py` tab with a simple chat UI, calling the new endpoint.
- Verify: a fixed set of Q&A test prompts (e.g. "what's the limit on walleye in zone 27", "can I eat a 45cm pike from Lac X", "best lure for smallmouth in July") checked for correct tool-routing and no hallucinated numbers when the structured source is authoritative.

**Phase 3 — Map tab integration — COMPLETE (2026-07-27)**
- Overlay the zone polygons found in Phase 0 on the existing Map tab; clicking a zone shows its name + link to the official quebec.ca rules page for that zone (a live-scraped limits table embedded in a static Leaflet popup would mean re-scraping all 34 zones on every map render — the official-source link keeps this to one cached fetch, matching the pattern already used by the Identify cards).
- Plot nearby consumption-advisory sites as markers, reusing the same data as `consumption.py`.
- Built `GET /regs/zones/geojson` (in-process cached, zone polygons/names essentially never change) and `GET /regs/consumption/stations` (nearest-N sampling sites) in `omyfish-ai`'s `regs_advisor/router.py`; `StationOut` schema added. 5 new router tests (38 total in `omyfish-ai/tests/regs_advisor/`).
- `apps/omyfish_web/regs_client.py::fetch_zones_geojson`/`fetch_consumption_stations` + Map tab in `apps/omyfish_web/main.py` render a `folium.GeoJson` zone overlay (tooltip + popup) and green station markers (near the average of the user's own observation coordinates), plus a disclaimer caption. Verified end-to-end against the live government endpoints (33 real zone polygons, real nearby stations near Quebec City) and visually in a headless-browser render of the actual folium map output — see the Phase 3 completion note in the linked memory for screenshots/verification detail.

**Phase 4 — Maintenance — COMPLETE (2026-07-27)**
- QC regs republish ~annually (typically effective April 1) — added a maintenance-reminder docstring note directly above `ZONE_NAME_TO_ID` in `regs_advisor/engine/zones.py` to re-verify the zone table and limits-page HTML parsing each spring.
- Persistent disclaimer ("informational only — verify current regulations at quebec.ca") audited across every surface that shows a limit/consumption number: Identify cards and the Regs & Tips chat tab already had one (Phase 1/2); the new Map tab overlay got one added in this pass. All three `regs_advisor` response schemas (`LimitsResponse`, `ConsumptionResponse`, `AskResponse`) also carry a `disclaimer` field for any future API consumer.

## What to build first

1. ~~Phase 0 discovery~~ — done; both zone lookup and limits are confirmed live HTTP endpoints (see above).
2. ~~Phase 1 structured backend + Identify auto-cards~~ — **done 2026-07-27.** `regs_advisor/` built in `omyfish-ai` (`engine/zones.py`, `engine/limits.py`, `engine/consumption.py`, `providers/*`, `router.py`, `schemas.py`), wired into `main.py`, `GET /regs/limits` and `GET /regs/consumption` live and tested end-to-end against the real government endpoints. 26 tests in `tests/regs_advisor/` (unit + router-level with mocked providers). `identify_fish` in `apps/omyfish_api/routes/species.py` now folds in `legal_limit`/`consumption_advice` when coords are present (additive, degrades gracefully if the AI service is unreachable). Streamlit Identify tab (`save_observation_form` in `apps/omyfish_web/main.py`) renders the two info cards + disclaimer via the new `apps/omyfish_web/regs_client.py`. Bug caught during testing and fixed: the original size-bucket picker could borrow a smaller size class's meal count when the fish's actual class wasn't sampled — fixed to never do that (contaminant levels rise with size per the source data's own caveat).
3. ~~Phase 2 chat tab~~ — **done 2026-07-27.** `regs_advisor/engine/retrieval.py` (hand-rolled TF-IDF chunk retrieval over `knowledge_base/*.md` — chose this over sentence-transformers to avoid a new ML dependency + model download for a corpus this small; keyword overlap is a strong signal for domain terms like species names and zone numbers). Two curated KB files: `regulations_overview.md` (how zones/limits/consumption advisories work, in plain language, not verbatim legal text) and `species_tackle.md` (tackle/technique notes for ~12 common QC gamefish). `POST /regs/ask` (`providers/llm_client.py`, Claude API via the official `anthropic` SDK, model `claude-opus-5` by default — overridable via `REGS_CHAT_MODEL` env var — one non-streaming call per question, no agentic loop). New `apps/omyfish_web/regs.py` "Regs & Tips" chat tab wired into `main.py`'s tab bar, backed by `apps/omyfish_web/regs_client.py::fetch_ask`. 12 more tests added (33 total in `omyfish-ai/tests/regs_advisor/`) — retrieval ranking + router tests with the LLM call mocked (never hits the real API in CI). All 67 omyfish-python tests and all 33 omyfish-ai regs_advisor tests pass.
4. ~~Phase 3 Map overlay~~ — **done 2026-07-27.** `GET /regs/zones/geojson` + `GET /regs/consumption/stations` in `omyfish-ai`; Map tab in `omyfish-python` overlays zone polygons and consumption-site markers.
5. ~~Phase 4 Maintenance~~ — **done 2026-07-27.** Annual-reverification reminder added to `engine/zones.py`; disclaimer coverage confirmed on every surface.
6. **LLM provider swapped to Groq (2026-07-27).** `/regs/ask` was silently broken (no `ANTHROPIC_API_KEY` configured) and, separately, the failure mode wasn't even handled cleanly — a missing-key error is raised at `anthropic.Anthropic()` construction as a `TypeError`, which the original `except anthropic.APIError` didn't catch, so it leaked as an unhandled 500 instead of the intended 503. Per user request, `llm_client.py` now uses the `groq` SDK (`llama-3.3-70b-versatile` by default, still overridable via `REGS_CHAT_MODEL`) and catches the broader `groq.GroqError` (covers both client-construction and API-call failures) so any provider failure degrades to a clean `LLMError` → 503. Requires a `GROQ_API_KEY` env var wherever `omyfish-ai` runs.

## Phase 2 follow-ups (deliberately deferred, not forgotten)

- **No multi-tool routing yet.** `/regs/ask` is single-hop RAG only — it does not parse species/size/location out of the question to also call the Phase 1 `/regs/limits` or `/regs/consumption` endpoints. A question like "is a 40cm walleye near Lac Saint-Jean legal, and can I eat it?" gets a KB-grounded general answer, not the precise numeric one Phase 1's structured endpoints could give. The original plan flagged this as "a checkpoint, not a default" — revisit if/when that combined-lookup case comes up often enough to justify the added complexity (small, fixed 2-4 tool function-calling, not LangChain).
- **KB is intentionally narrow.** ~12 species covered in `species_tackle.md`, not all 118 in `fish_info.json`. Expanding coverage is pure content-writing, no code changes needed — just add more `## Species Name` sections to the markdown files.
