# Iguana Studio on pytincture — plan

Drafted 2026-10-27. The goal is a **frontend change, not a feature change.** Iguana keeps every
mode (Generate, Person, Refine, Edit, Animate), the prompt sidebar and its modifiers, saved
prompts, the LoRA stack, per-checkpoint tuning, FLUX/GGUF and Kontext, live progress + ETA, and
the gallery with its send-to-mode menu. What changes is the page: from one 2,594-line
`static/index.html` (≈675 lines CSS, 63 JS functions, 230 `<option>`s in markup) to a
**pytincture + wapyt** page (Python in the browser), the same stack as Pantheon, the AI
Ecosystem dashboard, Basilisk and Calagopus.

Why: one frontend stack across the ecosystem, Python on both sides of the wire, and the parts of
`index.html` that are really *data* — the modifier lists, per-checkpoint configs, mode
definitions — become Python data with one home instead of markup and string tests.

## Decisions to confirm

| Question | Recommendation | Why |
|---|---|---|
| Structure | **In place, phased.** Same repo, image, container, port 7862. The new page is served beside the old one (`/` stays old, `/iguana/` new) until parity; then the old page is deleted. | Worked for Pantheon (Phases 0–7 in a day) and lets every phase ship without breaking the tool. |
| Network | **Loopback only** (`127.0.0.1:7862`), like the dashboard. | Today Iguana is published on `0.0.0.0:7862` with **no login** — anyone on the LAN can generate and delete outputs. pytincture's `allowed_hosts` makes that an explicit choice. If LAN use matters, it needs auth first (Pantheon's `services/auth.py` / pytincture's login hook), as a later phase. |
| Look | **Keep Iguana's dark violet look**, rebuilt on wapyt widgets and a stylesheet. | It's a tool, not a companion app; users know where things are. Not a redesign. |
| Progress | **`@bff_stream` instead of 2 s polling.** | Pushes phase/step/ETA as they happen. Needs the stream limits handled for video (see risks). |
| CLI | `run.py` and `workflows/` untouched. | No business logic moves. |

## What does not change

- `workflows/*` (graph builders), `client.py` (queue, websocket progress, downloads), `run.py`.
- The ComfyUI contract, `outputs/` and `data/saved-prompts.json` (same file, same format).
- The `localStorage` key **`studio_v1`** and its field ids — reused so nobody loses their state at
  switch-over. New-page state reads the same blob.
- The `iguana` container name, `stack iguana`, the `ai-net` network.

## Architecture

```
browser: appcode/iguana.py (Pyodide + wapyt)
   ├─BFF──▶ appcode/bff/studio.py   ──▶ services/jobs.py ──▶ workflows/* + client.py ──▶ ComfyUI
   │        (checkpoints, loras, prompts, gallery, generate, delete)
   ├─bff_stream──▶ job progress (phase, step/max, eta, done → files)
   └─plain HTTP──▶ POST /upload (multipart → upload id) · GET /outputs/{f} · GET /api/health
```

- **`server.py`'s job runner moves to `services/jobs.py`** (a plain module). BFF modules are
  re-executed on every call, so the `jobs` dict, the threads and the phase map must not live in a
  BFF file — the dashboard's test fails on module-level state in a BFF; copy it.
- **Binary stays off the BFF.** Uploads (source images, PhotoMaker photos — several MB each) go
  to a plain multipart `POST /upload` that stores into `temp/` and returns an id; `generate()`
  sends ids. Outputs are served by the existing `GET /outputs/{f}`; images belong in `<img src>`,
  not JSON.
- **One server, no auth.** No `@bff_policy` (it forces a policy hook), `allowed_hosts` =
  `127.0.0.1/localhost/::1`. pytincture's Origin/content-type checks replace nothing Iguana has
  today — they are new protection for the delete and generate endpoints.
- **Prompt composition moves to Python** (`appcode/ui/prompt.py`): `build_prompt()`,
  `active_prompt()`, the field order and the Person `img ` prefix, with the 230 modifier options
  as data in `appcode/ui/modifiers.py` (`{field: [(group, [(value, label)])]}`). The markup is
  generated from it. One place to add a lighting term.
- **Model rules have one home already** (`workflows/defaults.py`); the new page asks the server
  (`/checkpoints` returns `base`) instead of re-deriving, and the per-checkpoint configs
  (`CKPT_CONFIGS`, `_fluxConfig`) move server-side next to them.

## Current page → new page

| Today (`index.html`) | New (wapyt) | Notes |
|---|---|---|
| Left rail: prompt box, saved prompts, preview, LoRAs, 9 modifier selects | `sidebar` + `form` fields generated from `modifiers.py` | Sticky prompt block kept (CSS). |
| Mode tabs + per-mode panels | `tabwidget`, one panel module per mode (`ui/modes/*.py`) | Each mode declares its fields, defaults and which prompt it sends. |
| Checkpoint selects grouped by base | native `<select>` with `<optgroup>`s, filled from `/checkpoints` | Keep the "async select restore" rule from CLAUDE.md. |
| LoRA stack (ordered, move up/down, strengths) | small custom list component | Chain order is meaningful — keep numbering. |
| Dropzones (Person multi, Refine/Edit/Animate single) | `filetransfer` or a plain drop target → `POST /upload` | Thumbnails via `blob:` URLs. |
| Job card: spinner, phase, bar, ETA | `progressbar` + status line fed by the stream | Update in place (CLAUDE.md: replacing the card restarts the spinner). |
| Results + gallery (virtualised grid, "⋯" menu) | gallery grid + `contextmenu` | Virtualisation is the main risk (below). |
| `alert()`/`confirm()`/`prompt()` | `message.alert/confirm/prompt` | Consistent with Pantheon/dashboard. |
| Status dot (ComfyUI up?) | toolbar status, polled via BFF | 10 s, as today. |

## Phases

| # | Phase | Done when |
|---|---|---|
| 0 | **Spike** (risks below): pytincture in Iguana's process on Python 3.13; one BFF listing checkpoints; a real Generate job started by BFF with progress over `@bff_stream`; an upload through `POST /upload`; a 2,000-tile virtual gallery scrolled in Pyodide. | Each risk proven, or a fallback chosen. |
| 1 | **Shell + sidebar.** Layout, theme, status, prompt box, modifiers from `modifiers.py`, preview, saved prompts, `studio_v1` restore. | The prompt is composed identically to the old page (a test diffs `build_prompt()` against the JS for a fixed set of field states). |
| 2 | **Generate + Refine.** Checkpoint picker, per-checkpoint config, LoRA stack, negative, seed, submit, streamed progress, results. | Both modes generate end to end against ComfyUI (SDXL + FLUX GGUF). |
| 3 | **Person, Edit, Animate.** Uploads, multi-photo dropzone, Kontext instruction + guidance, WAN motion/length snapping (4n+1)/size, video results. | Each mode produces a real output. |
| 4 | **Gallery.** Virtualised grid, "⋯" menu (download, Refine/Edit/Animate, delete), send-to-mode, video tiles. | Parity with the old gallery at 2,000 items. |
| 5 | **Switch-over.** `/` serves the new page; delete `static/index.html` and the JSON routes only it used; publish on `127.0.0.1`; update `CLAUDE.md`; Playwright smoke test (every mode, zero console errors). | One UI. |
| 6 | *(optional, later)* LAN access behind auth + TLS. | Only if wanted. |

Each phase ends with the smoke test and screenshots, like `ai-stack/stack-ui/tests/smoke.py`,
plus one real generation per affected mode — the way FLUX and saved prompts were verified.

## Risks to retire in Phase 0

- **Gallery virtualisation in Pyodide.** Today a `scroll` handler re-renders the visible rows each
  frame (rAF-coalesced). Python ↔ DOM calls per frame may stutter. Measure with 2,000 tiles
  (outputs today: 41, but it is built for thousands). **Fallback:** keep the grid as a small JS
  island driven from Python by events, as Pantheon did for voice and the avatar.
- **Stream limits vs video jobs.** pytincture's BFF streams are bounded (Pantheon measured
  300 s total / 30 s idle); an Animate job can run 30 min (`VIDEO_TIMEOUT` 1800 s), and model
  loading can be silent for >30 s. Options: raise `BFF_STREAM_*`, send keepalive events from the
  job thread, or **reconnect by job id** (the stream is a view of `services/jobs.py`, so a new
  stream picks up where the last ended). Prefer reconnect — it also survives a page reload.
- **Thread jobs + event loop.** Jobs run in threads (sync `requests`/`websocket-client`); the
  stream must read their state without blocking the loop. Keep pytincture's default
  `event-loop` mode (Pantheon: never `worker-thread` / `isolated-process`).
- **Uploads.** Confirm a 10–20 MB multipart upload on a plain route coexists with pytincture's
  middleware (Host/Origin checks), and that `temp/` cleanup still runs per job.
- **CSP.** Thumbnails from `blob:` URLs and `<video>` playback of `/outputs/*.mp4` under
  pytincture's CSP.
- **Python 3.13 image.** Iguana's image is 3.12; pytincture needs 3.13+. Requirements are light
  (`requests`, `websocket-client`), so low risk — but the wapyt wheel build stages from the
  dashboard's `Containerfile` come along.

## Traps already paid for elsewhere (read before coding)

From Pantheon's and the dashboard's `CLAUDE.md` / `PYTINCTURE_PLAN.md`:
- BFF modules are re-executed per call → state in plain modules; import them *inside* methods;
  never import one BFF from another.
- Async exports have no `_async` twin; sync ones do.
- `get_cell()` returns a cell object → `container_of(cell)` before touching DOM.
- `[hidden]` loses to an element's own `display:` → restate `[hidden] { display:none }`.
- Never destroy a proxy inside its own callback.
- `overflow: clip`, not `hidden`, on fixed-height boxes (focus() scrolls `hidden` ones).
- Import *names* in browser code (`from ui.common import spawn`) — the packager follows only that.
- Build the wapyt wheel with `dev_wheel.sh appcode` for host dev; the image pins `WAPYT_REF`.

## Rough size

Old page ≈ 2,600 lines in one file. Expect ≈ 1,800–2,200 lines of Python across ~12 modules
(shell, sidebar, prompt, modifiers data, five mode panels, gallery, common) plus ~400 lines of CSS,
and a `services/jobs.py` + BFF of ~300. Phases 1–4 are each roughly a session; Phase 0 decides
whether the gallery stays a JS island.

## Decisions taken (2026-10-27)

The recommendations above, as proposed: in place and phased; **loopback only**; keep Iguana's
dark violet look; progress over `@bff_stream`; `run.py`/`workflows/` untouched.

## Phase 0 results (2026-10-27) — all risks retired

Spike: `service.py` (one server: pytincture + the classic routes), `services/jobs.py` (the job
runner, moved out of `server.py`), `appcode/bff/studio.py`, `appcode/iguana.py` (a bare test
page), run on the host (Python 3.13, `.venv`) against the live ComfyUI and KoboldCPP.

| Risk | Result |
|---|---|
| One server for both pages | ✅ `/` classic, `/iguana/` new, same process and job table. **The classic routes must go in FRONT of pytincture's** (`app.router.routes[0:0] = …`): pytincture registers a catch-all `/{application}` that otherwise swallows `/checkpoints`, `/prompts`, `/gallery`. The classic page works unchanged under pytincture's middleware: models listed, `POST/DELETE /prompts` and `POST /generate` 200, no console errors. |
| Jobs moved to `services/jobs.py` | ✅ The classic `/generate` + `/job` ran a real FLUX job through every phase (queued → encoding → sampling 1–4 with ETA → decoding → saving) in 16 s. `params_for()` is now shared by both pages. |
| BFF → job → progress stream | ✅ `Studio.generate()` + `Studio.follow()`: text2img in 8.7 s with every phase streamed. |
| Stream limits (300 s total, 30 s idle) vs 30-min video | ✅ `follow()` sends state on change plus a heartbeat every 5 s, and ends itself after a budget with `{"type":"continue"}`; the page calls it again. Proven with `IGUANA_STREAM_BUDGET=8`: the job reconnected once mid-run and finished normally. Default budget 240 s. A reload can resume a job the same way. |
| Thread jobs + event loop | ✅ default `event-loop` mode; `follow()` polls the job dict with `asyncio.sleep(0.5)`. |
| Uploads | ✅ `POST /upload` → ids → `generate(…, upload_ids)`; upload + img2img in 12 s, temp file removed after the job. **pytincture caps every request body at 16 MiB**, before any route: an 18 MB photo got 413. The `MAX_REQUEST_BODY_BYTES` env var does **not** change it; `PytinctureConfig(max_request_body_bytes=48 MiB)` does. Route limit 40 MB per file (413 with the file name); the page will upload one file per request. Non-images 400; foreign `Host` 400. |
| Gallery virtualisation in Pyodide | ✅ **Stays in Python, no JS island.** 2,000 tiles, 3 s of continuous scrolling: 180 renders, **1.0 ms median, 1.1 ms p95, 2.0 ms max** per render (rebuilding ~30 tiles via `innerHTML` each frame). |
| CSP | ⚠️ `img-src 'self' data: https:` — **no `blob:`**: `URL.createObjectURL` previews are blocked (seen in the console). Phase 3 previews uploads with `FileReader` → `data:` URLs. Videos: no `media-src`, so `default-src 'self'` covers `/outputs/*.mp4`. |
| Boot | 1.7 s to an interactive page with 14 models listed (warm cache). |
| Python 3.13 | ✅ everything installs (`requests`, `websocket-client`, `pytincture==1.0.0`, wapyt). The image still builds the classic page on 3.12 until Phase 5 (verified: test build imports `server` + `services.jobs`). |

Found along the way:

- **`js.window.__name` inside a class is name-mangled** to `js.window._Iguana__name` by Python,
  so JavaScript never sees it. Use names without leading double underscores.
- **The Containerfile copies files by name**, so `server.py` importing `services/` would have
  broken the next rebuild — `COPY services/ ./services/` added. `.containerignore` now skips the
  3.13 `.venv/` and the dev wapyt wheel.
- **The running `iguana` container is arm64 under emulation** (`uname -m` → `aarch64`): the
  cached `python:3.12-slim` is the ARM build (pulled 2026-09-19). Pre-existing, not from this
  work; fixed by pulling the amd64 base (`--platform linux/amd64`) — Phase 5's new 3.13 base
  will be pulled fresh anyway.
- `__pycache__/*.pyc` files are tracked in git and change whenever Python runs; keep them out
  of commits (they are in `.gitignore` but were committed before it).

## Phase 1 results (2026-10-27) — shell + prompt rail

`/iguana/` now has the classic page's top bar (ComfyUI status polled every 10 s; Generate
disabled until Phase 2), the full prompt rail and the five mode tabs; the workspace is a
placeholder.

| Module | What |
|---|---|
| `appcode/ui/modifiers.py` | The 9 modifier dropdowns as data — **generated from the classic markup**, so all 220 values carry over byte for byte (saved prompts and `studio_v1` store values). Edit here from now on. |
| `appcode/ui/prompt.py` | `build_prompt()` / `active_prompt()`, a line-for-line port of the JS; no browser imports, so it is testable anywhere. |
| `appcode/ui/sidebar.py` | The rail, built from `modifiers.py`: sticky prompt + Clear, saved prompts (wapyt dialogs: name prompt, replace/overwrite/delete confirms), preview, the four sections. |
| `appcode/ui/common.py` | `spawn`, `proxy`, `esc`, `failed`, and the shared `studio_v1` state (**merging** writes, so keys the new page doesn't manage yet survive). |
| `appcode/bff/prompts.py` | Saved prompts through `server.py`'s functions — one store for both pages. |
| `appcode/iguana.py` | The shell (top bar, layout, tabs, status). |
| `tests/test_prompt_parity.py` | The "done when" test. |

**Done-when met:** `tests/test_prompt_parity.py` drives both pages from one server with 60
random sidebar states (real option values; blank, whitespace-only, comma, quote, newline and
unicode text; all five modes) — **60/60 identical previews**. Plus: state written by the
classic page restores in the new one (fields + mode), and a prompt saved on the classic page
loads on the new one, negative included. The dialogs were driven for real (save → name →
select; load over different text → "Replace?" → restored; delete → empty list); no console
errors.

Found along the way:

- **wapyt's layout chrome** paints its own slate cells (`.wapyt-layout`, `.wapyt-cell`: bg
  `#1e293b`, 1 px border, 8 px radius). Overridden to Iguana's `--bg`, edge to edge.
- A saved prompt's **negative** is written straight into `studio_v1` until the Generate panel
  (Phase 2) owns the field; both pages read it from there.
- Loading over a sidebar whose *dropdowns* differ counts as "different" even when the text box
  is empty — matching the classic page, which compares every saved field.

## Phase 2 results (2026-10-27) — Generate + Refine end to end

| Module | What |
|---|---|
| `services/models.py` | Per-checkpoint recommended settings, **moved server-side** from the page's `CKPT_CONFIGS` (FLUX: schnell 4/1.0, dev 20/3.5; else tuned table, else base default). `Studio.checkpoints()` returns `[{name, base, config}]` + the default negative. |
| `appcode/ui/panels.py` | Generate + Refine control bars. Checkpoint selects grouped by base; the **two-step tuning rule** kept (`_apply_ui` on every boot — labels only; `_apply_config` only on an explicit change or a first visit), and an empty async select never overwrites a saved choice. Refine's source previews as a `data:` URL. |
| `appcode/ui/loras.py` | The LoRA stack in the rail: ordered chain, ↑/↓, ✕, strength −1…2, missing files kept and flagged but not sent; `__loras` shared with the classic page. Hidden outside Generate/Person/Refine. |
| `appcode/ui/jobs.py` | Job card (spinner, phase, step, %, ETA — rewritten in place), results, error card. Progress over `Studio.follow()`; the running job id lives in `sessionStorage`, so **a reload mid-job reconnects** and finishes. A job the server no longer knows (restart) says so. |
| `appcode/bff/studio.py` | `loras()`; `generate()` now **coerces numbers itself** (the classic route had FastAPI's `Form()` doing it; JSON doesn't). |

**Done-when met**, against the live ComfyUI with KoboldCPP loaded (dev server, port 7872):

| Run | Result |
|---|---|
| Empty prompt | "Write a prompt first." dialog, nothing queued |
| FLUX GGUF, explicit select | stamped 1024²/4 steps/guidance 1.0, label → Guidance, negative hidden |
| FLUX GGUF + LoRA @ 0.3 (768²) | **17.7 s**, every phase streamed. ComfyUI's history confirms the graph: `LoraLoader(model=["1",0] GGUF, clip=["1c",0] DualCLIPLoader)` feeding `ModelSamplingFlux` — the first end-to-end run of a LoRA on the split GGUF path |
| SDXL lightning, explicit select | stamped 6 steps/CFG 2, label → CFG, negative shown; **7.3 s** |
| Refine, uploaded source, FLUX @ 0.7 | `data:` preview; **13.7 s** |
| Reload mid-job | reconnected by job id, finished **10.8 s** after the reload; `sessionStorage` cleared |
| Classic page afterwards | shows the same model, size, denoise and prompt (shared `studio_v1`) |
| Prompt parity (Phase 1 test, re-run) | still 60/60 |

No console errors. Test outputs were deleted afterwards.

Found along the way:

- `ModelSamplingFlux` had no phase label, so Refine briefly showed the raw class name — added
  ("preparing model") to the shared `PHASES` in `services/jobs.py`.
- The LoRA phase is too quick to see on a warm run; the history check above is how to
  confirm a LoRA was applied.

## Phase 3 results (2026-10-27) — Person, Edit, Animate

All five modes now run from `/iguana/`. `ui/panels.py` gained the three control bars, one
reusable single-image source picker (Refine/Edit/Animate), and Person's multi-photo dropzone
(click or drag, `data:` thumbnails, click to remove). The Edit instruction and Animate motion
boxes are real fields now and drive the preview; `iguana.py` runs each mode with the classic
page's checks (source image, instruction, motion, at least one photo) and uploads **one
request per file** (pytincture's body cap). `snap_length()` mirrors `video.clamp_length()`
for the "81f · 3.4s" label — checked equal for every length from −5 to 140.

Against the live ComfyUI, KoboldCPP still loaded:

| Run | Result |
|---|---|
| Edit — Kontext, 12 steps, "make it winter…" | **56 s**; snow added, lighthouse, wall and framing kept |
| Person — PhotoMaker V2, 1 reference (a FLUX-generated fictional face), 768×1024, 20 steps | **25 s**; face pipeline ran (InsightFace + PhotoMaker loaders in the phase list) |
| Animate — WAN 2.2 5B, 640², 9 frames @ 8 fps, 6 steps | **21 s**; `<video>` plays (readyState 4, 640 px, 1.125 s) — so `default-src 'self'` covers `/outputs/*.mp4` |
| Validation | each mode's dialog fired with its message; nothing queued |
| LoRA section | shown in Generate/Person/Refine, hidden in Edit/Animate |
| Prompt parity (re-run, Edit/Animate boxes now real fields) | 60/60 |

No console errors; every upload removed from `temp/` after its job; test outputs deleted.

Found along the way:

- **The classic page sent Animate the image negative.** Its generate() appends the Generate
  panel's `neg-prompt` (default: the long SD negative) for `img2vid`, in a mode that doesn't
  even show that box — so `video.NEGATIVE_VIDEO`, tuned by measurement *not* to suppress
  motion (+~25% motion), was never used from the GUI. The new page sends an empty negative
  for Animate, so the server's video negative applies. The classic page is left as is; it goes
  in Phase 5.
- **PhotoMaker's likeness is weak** on SDXL base with one reference: the result was a
  plausible captain but not recognisably the reference face. Same server graph as the classic
  page — not a port issue. More (and varied) reference photos, or a stronger base, is the
  lever; noted, not fixed here.
- More raw class names in the status line (`PhotoMakerInsightFaceLoader`,
  `PhotoMakerLoaderPlus`) — labels added to the shared `PHASES`.
- WAN 5B ran at a tiny size beside KoboldCPP (8.8 GB held); a full 1280×704 × 81-frame clip
  will still want `Release VRAM` / KoboldCPP stopped first, as `CLAUDE.md` says.

## Phase 4 results (2026-10-27) — gallery + item menu

| Module | What |
|---|---|
| `appcode/ui/gallery.py` | `GalleryView`: collapsible section that takes over the workspace when open; virtualised (only visible rows + 2 overscan are built), geometry read from `--gtile/--gitem-h/--ggap`; video tiles. `ItemMenu`: one `position: fixed` menu on `<body>` for tiles **and** result cards — right-aligned to its button, flips above when there's no room, closes on outside click / Escape / scroll / resize, same button toggles. Names travel as escaped `data-` attributes. |
| `appcode/bff/gallery.py` | `items()` / `delete()` through `server.py`'s own functions (same rules as the classic page). |
| `Studio.from_output()` + `service.upload_from_output()` | **Send to Refine/Edit/Animate is server-side**: the gallery image is copied into `temp/` as an ordinary upload id. The classic page downloaded the file into the browser and re-uploaded it. The copy matters — jobs delete their source when they finish. |

Verified (dev server, live ComfyUI): header count = files on disk (48); open hides the output
area; menu lands right-aligned 4 px under its button, closes on toggle, Escape and outside
click; **Refine from the gallery** switched mode, closed the gallery, set the source and ran
(22 s) — **the original file was still on disk** afterwards and `temp/` was empty; deleting a
result from its card's menu removed the file, the card and the count; parity test still 60/60;
no console errors.

**2,000 items** (2,000 hard links to one output, removed afterwards): count 2,048, scroll
height exact (49,822 px for 293 rows), ~50–60 tiles in the DOM at any time. Scroll smoothness,
200 steps, old page vs new:

| | images blocked | images loading |
|---|---|---|
| classic | p95 16.7 ms, 0 frames > 50 ms | p95 50.1 ms, 20 > 50 ms |
| new | p95 16.8 ms, 0 frames > 50 ms | p95 66.6 ms, 30 > 50 ms |

With image loads blocked both pages hold 60 fps with no drops — **the Python render is not
the cost**. The stutter, on both pages, is decoding full-size 1024 px PNGs into 140 px tiles
(the hard links all have different URLs, so nothing is cached). **Follow-up worth doing
after switch-over:** a cached thumbnail route (Pillow, small WebP/JPEG per output) — it would
help far more than anything in the grid code.

Found along the way:

- **`float("140px")` fails in Python** where JS `parseFloat` returns 140 — the first gallery
  render raised on `getComputedStyle` values. `gallery.px()` parses CSS lengths.

## Phase 5 results (2026-10-27) — switch-over: one UI

- **Golden prompt test first.** Before deleting the classic page, 200 random sidebar states and
  the prompt its `buildPrompt()/activePrompt()` produced for each were captured into
  `tests/prompt_golden.json`; `tests/test_prompt.py` (pytest, no browser, 0.05 s) holds
  `ui/prompt.py` to them for good. The browser parity test that needed the classic page is gone.
- **Deleted:** `static/index.html`, and the routes only it used (`/`, `/comfy-status`,
  `/generate`, `/job/{id}`, `/checkpoints`, `/loras`, `/gallery`, `DELETE /outputs/{f}`,
  `/prompts*`). `server.py` keeps the functions the BFFs call as plain functions, plus
  `GET /outputs/{f}` and `/debug/*`; `python server.py` now runs `service.py`.
- **`/`** → 302 → `/iguana/` (pytincture's default-application redirect).
- **Image:** `python:3.13-slim`, **`--platform linux/amd64`** (Containerfile `FROM --platform`
  and `run-podman.sh`), the wapyt wheel stages from stack-ui (server wheel installed, browser
  wheel copied into `appcode/`), `CMD python service.py`, HEALTHCHECK on `/api/health`.
  Requirements: `pytincture==1.0.0`, `uvicorn[standard]`, plus the old ones.
- **Network:** published on **`127.0.0.1:7862`** (was `0.0.0.0`), `IGUANA_HOST=0.0.0.0` inside.
- **ai-stack:** the `stack` registry probes `http://localhost:7862/api/health` (was `/`).
- **Docs:** `CLAUDE.md` — run/dev instructions, env vars (`IGUANA_HOST`,
  `IGUANA_STREAM_BUDGET`), structure, a "pytincture page" section mapping every classic
  function to its new home, API table, design decisions. Global `~/.claude/CLAUDE.md` row.
- **`tests/smoke.py`**: health + `/` + foreign-Host check, every mode's control bar, gallery +
  item menu, zero console errors; `SMOKE_GENERATE=1` adds a real FLUX job (deletes its output).

Verified on the **real container**: `uname -m` → **x86_64** (was aarch64 under emulation),
Python 3.13.18, port `127.0.0.1:7862` only — `http://192.168.1.50:7862` (the LAN address) is
unreachable; `stack status` shows iguana up; smoke test **PASS** with a FLUX generation in
5.6 s; no errors in the container log; 201/201 golden prompt tests.

The browser state key (`studio_v1`) and `data/saved-prompts.json` carried over unchanged, so
settings and saved prompts from the classic page are still there.

## Follow-ups (not in this migration)

- ✅ **Gallery thumbnails** (done 2026-10-27) — `GET /thumbs/{f}?v=<mtime>`: a 280 px WebP per
  output image (~7.5 KB vs ~1.1 MB), cached in `outputs/.thumbs/`, warmed at start and after each
  job. 2,000 tiles: scroll p95 66.6 → **16.7 ms**, frames > 50 ms 30 → **0**; in-view tiles
  painted 0.1 s after scrolling stops (warm). Cold-only caveat: flinging through thousands of
  never-seen files queues their generation (~126 ms each) — which the warming makes rare.
- **PhotoMaker likeness** is weak on SDXL base with one reference (Phase 3) — more varied
  references or a stronger base; a model question, not a GUI one.
- **LAN access** (Phase 6 in the table above) only behind auth + TLS, if ever wanted.
