# Stripsmith Architecture

Stripsmith turns a plain-text story into an AI-generated comic. The same
six-stage pipeline (`src/`) is driven by two front ends: a local **CLI** and a
**web app** (FastAPI backend + React frontend) where users bring their own API
keys.

```
                        ┌──────────────────────────────┐
   CLI  ───────────────▶│                              │
   scripts/             │      Pipeline (src/)         │
   generate_comic.py    │   Stage 0 → 1 → 2 → 3 → 4 → 5 │
                        │                              │
   Web  ───────────────▶│                              │
   frontend (React)     └──────────────────────────────┘
        │  HTTP                      ▲
        ▼                            │ user-supplied API keys
   backend/main.py (FastAPI) ── ComicGenerator (backend/api_wrapper.py)
        │
        └── JobManager (backend/jobs.py): in-memory sessions + jobs
```

## The pipeline (`src/`)

The pipeline is plain Python with no web/CLI dependencies. Each stage is a class
that takes config + inputs and returns plain dicts / writes files.

| Stage | Module | Responsibility | External API |
|------:|--------|----------------|--------------|
| 0 | `analysis/normalizer.py` | Clean whitespace, normalize quotes, split paragraphs, detect chapters/dialogue, extract metadata | — |
| 1 | `analysis/analyzer.py` (`NarrativeAnalyzer`) | Extract chapters, characters, environments, art style as structured JSON | **Claude** |
| 2 | `assets/templates.py` + `assets/generator.py` | Build reusable per-character prompt templates, then render reference sheets | **DALL·E 3** |
| 3 | `panels/breakdown.py` (`PanelBreakdown`) | Break each chapter into pages/panels with dialogue, camera angles, layouts | **Claude** |
| 4 | `assets/generator.py` (`ImageGenerator`) | Generate each panel image, reusing character templates for consistency | **DALL·E 3** |
| 5 | `compositor/layout.py` + `compositor/export.py` | Place panels into page layouts; export to PDF / PNG / CBZ | — |

Stages 1 and 3 call Claude; stages 2 and 4 call DALL·E 3. Intermediate artifacts
(project spec, panel breakdowns, panel images, composed pages) are written under
`data/temp/` so a run can be inspected or resumed stage-by-stage.

Four data-flow contracts are load-bearing and easy to break:

- **Stages 1 and 3 must see the same text.** Stage 1 records chapter boundaries
  as paragraph indices into the *normalized* text; Stage 3 slices a chapter out
  by those indices, so it must be handed the same normalized text (not the raw
  story) or it extracts the wrong paragraphs.
- **Panel image filenames are chapter-scoped.** `global_panel_num` from the
  breakdown restarts at 1 each chapter, so Stage 4 writes (and Stage 5 reads)
  panels via `panel_image_name(chapter, n)`; an unscoped name silently overwrites
  earlier chapters' panels. The project's art style is also threaded into every
  panel prompt so backgrounds match the characters' look.
- **Page layout must hold every panel on the page.** Stage 4 generates (and
  pays for) one image per panel the breakdown placed on a page, and Stage 5's
  `compose_page` `zip`s those images against the rectangles from
  `_calculate_panel_positions`. That function therefore returns exactly one
  rectangle per panel for *every* layout — the grid grows extra rows past a
  template's nominal capacity (3/4/1/6) rather than capping, because a capped
  list would make `zip` silently drop the surplus panels off the page.
- **Character-sheet filenames must stay flat.** Stage 2 writes one reference
  image per character per angle into the character's directory. The default
  angles include `3/4`, whose slash would turn `{name}_{angle}.png` into a
  nested `{name}_3/` directory holding `4.png`, scattering the sheet. Names and
  angles are run through `ImageGenerator._sanitize_filename`, which maps
  path-unsafe characters to `-` (never dropping them, never emitting an empty
  name) so each part stays a single, separator-free component.

### Shared infrastructure (`src/utils/`)

- **`config.py`** — loads `config/config.yaml`, exposes dot-notation `get()`
  (e.g. `config.get("image.size")`). Also the single source of truth for the
  default Claude model (`DEFAULT_LLM_MODEL`) and output-token cap
  (`DEFAULT_LLM_MAX_TOKENS`), so the in-code fallback can't drift from the YAML.
- **`logger.py`** — colored console logging via `colorama`, optional file log.
- **`pipeline.py`** — small pure helpers shared by both front ends so they stay
  in sync: `select_chapters()` interprets the `--chapters`/web selector
  (`"all"`, `"N"`, `"N-M"`) with friendly validation, and `panel_image_name()`
  produces chapter-scoped panel filenames (panel numbering restarts per chapter,
  so filenames **must** include the chapter or multi-chapter panels collide).

### Model configuration

The Claude model is set in `config/config.yaml` under `analysis.llm_model`
(default `claude-opus-4-8`) and read by both `NarrativeAnalyzer` and
`PanelBreakdown`. To switch models (e.g. to a cheaper one for high volume), edit
that one value. DALL·E 3 settings (size, quality, style) live under `image:`.

## CLI front end (`scripts/generate_comic.py`)

A `click` app. `generate` runs stages 0→5 for a story file, with flags to stop
early (`--analyze-only`, `--characters-only`), pick chapters, choose output
format, and confirm cost before image generation. `test` checks API
connectivity. Keys come from `.env` (loaded via `python-dotenv`).

## Web front end

### Backend (`backend/`, FastAPI)

- **`main.py`** — HTTP API: create session, store keys, start generation
  (background task), poll status, download result, cancel. CORS-enabled for the
  Vercel frontend. A `lifespan` task periodically prunes old jobs/sessions
  (cancelled cleanly on shutdown). The download endpoint packages **directory**
  outputs into a single `.zip` before serving: the `png` format writes a folder
  of page images, and `FileResponse` can only stream a regular file (it raises
  on a directory), so a naïve hand-off broke every PNG download.
- **`api_wrapper.py`** (`ComicGenerator`) — async wrapper that runs the `src/`
  pipeline with the **user's** API keys (never the server's), reporting progress
  to the `JobManager` and offloading blocking SDK calls via `asyncio.to_thread`.
  Outputs are written under `data/temp/<job_id>/` and `data/output/<job_id>/`.
- **`jobs.py`** (`JobManager`) — thread-safe in-memory store of sessions
  (holding the per-user API keys, **memory only, never persisted**) and jobs
  (progress/status). Sessions expire after 2 hours; a background loop prunes
  expired entries. All mutation is guarded by a single non-reentrant lock —
  helpers therefore must not call each other while holding it.

### Frontend (`frontend/`, React + Vite)

A single-page app (`src/App.jsx`): enter keys → upload story + options → poll
progress → download. Talks to the backend at `VITE_API_URL`.

## Data flow & storage

- `data/stories/` — input stories (sample included).
- `data/temp/` — intermediate artifacts (project spec JSON, panel breakdowns,
  character sheets, panel images, composed pages). Gitignored.
- `data/output/` — final comics (PDF/PNG/CBZ). Gitignored.

No database: the CLI is stateless (files only); the web backend keeps session
and job state in memory and is therefore single-process (horizontal scaling
would require externalizing `JobManager`).

## Deployment

- **Backend** → Railway (`railway.json`, `Procfile`, `backend/runtime.txt`).
- **Frontend** → Vercel (`frontend/vercel.json`).

See `DEPLOYMENT.md` and `WEB_README.md` for specifics.

## Testing

`tests/` (pytest) covers the pure-Python units — normalizer, config, templates,
layout geometry, the `JobManager`, and the web key-wiring — fully offline (no API
keys or network). See the Testing section of the README.

## Known constraints

- In-memory web state ⇒ single backend process; restart loses in-flight jobs.
- Character consistency depends on DALL·E 3 prompt templating (no fine-tuning).
- `opencv-python` is listed in `requirements.txt` but not yet used (reserved for
  the planned automatic speech-bubble placement in Phase 2).
