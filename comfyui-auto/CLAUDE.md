# Iguana Studio (comfyui-auto) — Project Context

## What this is
A Python toolkit + web GUI that drives ComfyUI over its HTTP API. No clicking around in
ComfyUI's node editor — you write a prompt, the GUI submits a generated workflow graph,
follows its progress, and saves the result.

**The GUI is a pytincture + wapyt page since 2026-10-27** (Python in the browser, like
Pantheon and the AI Ecosystem dashboard). It replaced the 2,594-line `static/index.html` in a
phased, behaviour-for-behaviour port — plan, measurements and decision log in
**`PYTINCTURE_PLAN.md`**. Much of the GUI write-up below predates the port and still names the
old JavaScript functions; the behaviour is the same, and
[The pytincture page](#the-pytincture-page) maps each old name to its new home.

Facts below were verified against the running stack on **2026-08-10**. Where the code and
reality disagree, that's called out explicitly under [Known broken / stale](#known-broken--stale).

## Runtime topology

| Piece | Where | Reached at |
|---|---|---|
| **iguana GUI** | Podman container `iguana` on network `ai-net` | host `http://localhost:7862` |
| **ComfyUI** | Podman container `comfyui` on network `ai-net` | `comfyui:8188` (from inside `ai-net`) |
| ComfyUI data | bind mounts from `~/Development/ai_ecosystem/ComfyUI/` | `/data/{models,custom_nodes,input,output,user}` |
| `outputs/` | bind mount from the repo dir | `/app/outputs` |
| `data/` | bind mount from the repo dir (gitignored) | `/app/data` — `saved-prompts.json` |

ComfyUI is a **container on `ai-net`**, not host networking — `comfyui:8188` only resolves on
that network, so joining `ai-net` is required, not optional. (`host.containers.internal` was the
old path and no longer applies.)

## How to run

**Containerized (default — via the ai-stack launcher).**
```bash
stack up                     # bring up backends (koboldcpp + comfyui) first
stack iguana                 # build on first run, then start on :7862
                             #   (directly: ./run-podman.sh [--rebuild] [--port N])
# open http://localhost:7862 · logs: podman logs -f iguana · stop: stack down iguana
```

**Host dev (`.venv`, Python 3.13)** — iterate without rebuilding the image. 7862 is the
container's, so use another port; ComfyUI is reached on the host's published 8188:
```bash
uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -r requirements.txt pytest \
    ~/Development/Pytinc/wa_pytincture_widgetset
PYTHON=$PWD/.venv/bin/python ~/Development/Pytinc/wa_pytincture_widgetset/scripts/dev_wheel.sh appcode
COMFY_HOST=localhost PORT=7872 .venv/bin/python service.py      # → http://127.0.0.1:7872/
.venv/bin/python -m pytest -q tests                             # prompt golden test (no browser)
IGUANA_URL=http://127.0.0.1:7872 CHROME=~/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome \
  [SMOKE_GENERATE=1] uv run --with playwright python tests/smoke.py   # every mode, 0 console errors
.venv/bin/python run.py text2img "a cat"                        # CLI (see caveats below)
```
The old `venv/` (Python 3.12) only ran the classic page and can be deleted.

### Environment variables
| Var | Default (container) | Purpose |
|---|---|---|
| `COMFY_HOST` | `comfyui` | ComfyUI hostname |
| `COMFY_PORT` | `8188` | ComfyUI port |
| `PORT` | `7862` | Port the GUI binds |
| `IGUANA_HOST` | `0.0.0.0` in the container, `127.0.0.1` on the host | Bind address. The container is published on **all interfaces** with no host check and no login: Iguana is a local tool for whoever installs it, so any device on the LAN opens `http://<host>.local:7862`. |
| `IGUANA_STREAM_BUDGET` | `240` | Seconds a progress stream runs before it hands over to a fresh one (pytincture caps streams at 300 s). |

The startup banner derives its printed URL from the same `PORT` value it binds, so the two can't
drift apart. (It used to hardcode 7861 — the **companion** app's port; iguana is 7862.)

## Project structure
```
comfyui-auto/
├── service.py           # THE server: pytincture app + plain routes (/upload, /api/health)
├── server.py            # server-side functions the BFFs call + GET /outputs/{f}, /debug/*
├── services/
│   ├── jobs.py          # job table, threads, params_for(), progress view/ETA (was in server.py)
│   └── models.py        # per-checkpoint recommended steps/CFG/size (was the page's CKPT_CONFIGS)
├── appcode/             # pytincture modules_path — the page
│   ├── iguana.py        #   shell: top bar, layout, mode tabs, generate/upload, wiring
│   ├── ui/              #   browser-only modules (see "The pytincture page")
│   ├── bff/             #   studio.py (models, jobs, progress stream) · prompts.py · gallery.py
│   ├── static/iguana.css#   served at /istatic
│   └── wapyt-*.whl      #   the BROWSER's wapyt (git-ignored; dev_wheel.sh / the Containerfile)
├── tests/               # test_prompt.py + prompt_golden.json · test_zimage.py · smoke.py (Playwright)
├── run.py               # CLI alternative (text2img / img2img / video only)
├── client.py            # ComfyUI API client: queue, poll /history, download /view
├── workflows/
│   ├── defaults.py      # shared negative prompts + is_flux() / is_sdxl() detection
│   ├── lora.py          # splices a LoraLoader chain into any checkpoint-based graph
│   ├── text2img.py      # text → image; delegates to flux.py / zimage.py by base
│   ├── img2img.py       # edit an image; same delegation
│   ├── flux.py          # FLUX.1 graphs (build + build_img2img)
│   ├── zimage.py        # Z-Image graphs, Turbo and base (build + build_img2img)
│   ├── photomaker.py    # person from reference photos  ← see Known broken
│   ├── kontext.py       # Flux Kontext instruction editing (Edit mode)
│   └── video.py         # WAN 2.2 image→video + text→video
├── outputs/             # generated files (volume-mounted, gitignored); .thumbs/ = gallery WebPs
├── data/                # saved-prompts.json (volume-mounted, gitignored)
├── temp/                # uploads (up-<hex>.png), deleted after each job / swept after 1 h
├── Containerfile        # python:3.13-slim amd64 + wapyt wheel stages, HEALTHCHECK /api/health
└── run-podman.sh        # build (amd64) + run on ai-net, published on all interfaces
```

## The pytincture page

`service.py` builds the pytincture app and puts its few plain routes **in front of**
pytincture's own (pytincture registers a catch-all `/{application}` that would swallow
one-segment paths). `/` redirects to `/iguana/`. Everything request/response goes through
BFF classes; binary stays plain HTTP (`POST /upload`, `GET /outputs/{f}`).

| Classic (`index.html`) | Now |
|---|---|
| `buildPrompt()` / `activePrompt()` | `appcode/ui/prompt.py` `build_prompt()` / `active_prompt()` — guarded by `tests/test_prompt.py` against 200 outputs captured from the classic page |
| the 9 modifier `<select>`s (220 options) | `appcode/ui/modifiers.py` — data, generated from the old markup; **add options here** |
| sidebar, saved prompts | `appcode/ui/sidebar.py` (+ `bff/prompts.py`) |
| LoRA stack (`renderLoras`, `activeLoras`, `LORA_MODES`) | `appcode/ui/loras.py` |
| control bars, `applyCheckpointUI/Config`, `loadCheckpoints`, source pickers, Person dropzone, `updateAnimateLength` | `appcode/ui/panels.py` (`_apply_ui` / `_apply_config`, `snap_length`) |
| `CKPT_CONFIGS`, `_fluxConfig` | `services/models.py` `config_for()` (server-side; `Studio.checkpoints()` returns it) |
| `generate()`, `pollJob`, job card, `showOutputs`, `showError` | `appcode/iguana.py` `generate()` + `appcode/ui/jobs.py` (progress **streamed**, see below) |
| gallery (`galleryItems`, `renderGalleryWindow`), `openItemMenu`, `deleteOutput` | `appcode/ui/gallery.py` (`GalleryView`, `ItemMenu`) + `bff/gallery.py` |
| `set*FromGallery` (fetch blob → re-upload) | `Panels.set_from_output()` → `Studio.from_output()` copies the output into `temp/` server-side |
| `PERSIST_IDS`, `saveState/loadState` | `ui/common.py` `load_state/save_state` (same `studio_v1` key, merging writes) + each module's own ids |
| `/generate`, `/job/{id}`, `/checkpoints`, `/loras`, `/gallery`, `/prompts`, `/comfy-status` | BFF methods (`Studio`, `Prompts`, `Gallery`); those routes are gone |

What changed on purpose (details in `PYTINCTURE_PLAN.md`):
- **Progress is streamed** (`Studio.follow()`, a `@bff_stream`): state on change plus a 5 s
  heartbeat; the stream ends itself after `IGUANA_STREAM_BUDGET` with `{"type":"continue"}` and
  the page calls it again — that is how a 30-min video gets past pytincture's 300 s stream cap.
  The running job id is in `sessionStorage`, so **a reload mid-job reconnects**.
- **Animate sends an empty negative**, so `video.NEGATIVE_VIDEO` applies. The classic page sent
  the Generate panel's image negative to video jobs, silently overriding the tuned one.
- **Previews are `data:` URLs** (FileReader): pytincture's CSP has no `blob:` in `img-src`.
- **Uploads go one file per request**; pytincture caps request bodies — 48 MiB here via
  `PytinctureConfig(max_request_body_bytes=…)` (the `MAX_REQUEST_BODY_BYTES` env var does *not*
  change it). `/upload` takes ≤ 40 MB per image.
- **The item menu is built from escaped `data-` attributes** read by delegated listeners (no
  inline handlers, no closures over names) — still no way for a quote in a filename to break out.
- wapyt's layout chrome is overridden (`.wapyt-layout`, `.wapyt-cell`) to keep Iguana's look.

**Gallery thumbnails** (`server.thumb_path` / `get_thumb` / `warm_thumbs`): tiles load a 280 px
WebP (short side, for the 140 px cover-cropped tile; ~7.5 KB vs a ~1.1 MB PNG), made on first
request and cached in `outputs/.thumbs/` (hidden from the gallery listing; survives rebuilds;
rebuilt when the source is newer; deleted with it). `warm_thumbs()` runs once in the background
at start and for each job's outputs as it finishes, because on-demand is ~126 ms each and a
first fling through 2,000 uncached tiles queued 1,400 of them behind the ones in view.
Measured at 2,000 tiles: scroll p95 **16.7 ms, 0 frames > 50 ms** (full PNGs: 66.6 ms, 30), and
in-view tiles painted 0.1 s after scrolling stops. Videos keep `<video preload=metadata>` (no
ffmpeg in the image). Clicking a tile still opens the full image.

Traps: BFF modules are re-executed per call (state lives in `services/*`); a `js.window.__x`
inside a class is name-mangled by Python; `float("140px")` fails where JS `parseFloat` works
(`gallery.px()`); never destroy a proxy inside its own callback.

## The GUI

A left rail holds the **manual prompt box** and a handful of modifier dropdowns; a right panel
holds mode-specific generation controls; below sits the output view and a gallery.

**The prompt is written by hand.** As of 2026-08-27 the rail is prompt-first: you type the subject
into the textarea and the remaining dropdowns only *append* modifiers to it. The old
character-builder combos for gender, age, build, skin tone and hair were removed — describing a
person in free text is more expressive than picking from fixed lists, and the lists were the thing
standing between the user and the prompt. What survives (Face, Clothing, Scene, Pose & Focus) is
kept for the terms that are fiddly to retype, and **every one of them now defaults to `—` (off)**,
so a fresh session composes exactly what you typed and nothing else.

**Art style** is the one preset kept deliberately broad (18 terms under four `<optgroup>`s:
Photographic / Digital & cinematic / Illustration / Traditional media). The photographic group
leads because film-stock terms — `35mm film photography`, `analog photograph`, `candid snapshot` —
shift the model's grain and colour response rather than just relabelling the subject, which makes
them the most effective realism tokens on the photoreal SDXL checkpoints. `hyperrealistic` was
dropped as a near-duplicate of `photorealistic`. Genre words (cyberpunk, steampunk, gothic) are
kept **out** of this list on purpose: they describe a world, not a medium, so they belong under
Scene where they won't fight Setting.

Caveat — **Pony Diffusion V6 XL largely ignores plain style words.** It is trained on
`score_9, score_8_up, source_anime`-style tags, so terms from this dropdown underperform on that
checkpoint specifically; type the score tags into the manual prompt instead.

**Setting** got the same treatment as Art style — 29 places under four `<optgroup>`s (Studio &
interior / Outdoor & nature / Urban / Fantasy & sci-fi), replacing the original nine. Genre
aesthetics live here rather than under Art style, expressed as **concrete places** rather than
floating vibes: `in a neon-lit cyberpunk alley`, `in a gothic cathedral`, `in a medieval tavern`.
Phrased that way they are settings, so they compose cleanly instead of competing with the medium
term coming from Art style.

**Lighting** likewise went 6 → 25 under four `<optgroup>`s (Natural / Studio / Dramatic &
cinematic / Coloured & artificial). Unlike Art style and Setting, **all six original values were
kept verbatim**, so no saved state was invalidated by this one. The studio and dramatic groups use
real photographic lighting names — `Rembrandt lighting`, `chiaroscuro lighting`, `high key` /
`low key` — because the training captions use them too, so they land harder than a vague
"moody lighting" would.

Note that Lighting and Setting can contradict each other (`moonlight` + `in a kitchen`). Nothing
guards against it; the dropdowns are independent by design and the manual prompt is the place to
resolve any conflict.

**Every remaining dropdown got the same pass** on 2026-08-27, and from Lighting onward **all
original values were kept verbatim** — only Art style (`hyperrealistic` dropped) and Setting
(re-worded to carry prepositions) invalidated saved selections.

| Field | Was | Now | Groups |
|---|---|---|---|
| Art style | 6 | 18 | Photographic · Digital & cinematic · Illustration · Traditional media |
| Setting | 9 | 29 | Studio & interior · Outdoor & nature · Urban · Fantasy & sci-fi |
| Lighting | 6 | 25 | Natural · Studio · Dramatic & cinematic · Coloured & artificial |
| Camera | 6 | 20 | Framing · Angle · Lens |
| Clothing | 14 | 36 | Casual · Formal · Costume & genre · Swim & active · Lingerie & revealing · Undressed |
| Pose | 16 | 30 | Standing · Seated & reclining · Action · Intimate |
| Focus | 7 | 14 | Portrait · Body · Explicit |
| Expression | 9 | 24 | Warm · Composed · Distressed · Sensual |
| Eye colour | 8 | 15 | Natural · Striking |

Two conventions hold across all of them:
- **Explicit options are grouped, not scattered** — Focus/Pose/Clothing keep theirs in a clearly
  labelled trailing group so the everyday options stay quick to reach.
- **Clothing values added after the first pass carry their own article** (`a tailored suit`,
  `a silk robe`) because `buildPrompt()` prepends a bare `wearing `. The original fourteen have no
  article (`wearing casual outfit`) and were left alone rather than re-worded, since changing them
  would discard saved state for no real gain.

The `<optgroup>` labels need explicit colours (`.field select optgroup`): the selects set
`appearance: none`, but the popup is browser-native, so without a rule the group headers render in
browser defaults — dark text on the dark theme, i.e. invisible.

**The app is named "Iguana Studio"** (it was generically "Character Studio" until 2026-08-11). The
name is written out in two places that must be changed together: `js.document.title` and the
topbar `<h1>` in `appcode/iguana.py` (`load_ui`). The `<h1>` deliberately keeps the second word
in a `<span>` — `.topbar h1 span` renders it muted against the accented first word, so any
rename should stay two words to preserve that. (The pytincture application *id* `iguana` — the
`/iguana/` path, `APP_ENTRYPOINT`, the `iguana` cookie namespace — is an identifier, not the name.)
The `localStorage` key stays `studio_v1` (renaming it discards saved state) — writes merge, and
stale keys in a saved blob are simply ignored on load.

**Five modes** (`MODES` / `TASK` in `appcode/iguana.py`), which map onto backend tasks:

| Mode | Task sent | Controls | Notes |
|---|---|---|---|
| **Generate** | `text2img` | checkpoint, LoRA stack, w/h, steps, cfg, seed, negative | The main path. Works. |
| **Person** | `photomaker` | PhotoMaker model, w/h, steps, cfg, multi-photo dropzone | Prepends trigger word `img`. Needs the PhotoMaker-Plus custom node — see below. |
| **Refine** | `img2img` | checkpoint, LoRA stack, denoise slider, steps, cfg, seed, source image | Source can be uploaded or picked from the gallery. |
| **Edit** | `kontext` | instruction box, guidance slider, steps, seed, source image | Flux Kontext instruction editing — see below. **Ignores the prompt sidebar.** |
| **Animate** | `img2vid` | source image, **motion box**, length, fps, size, steps, CFG, shift, seed | WAN 2.2 image→video — see below. **Ignores the prompt sidebar**, like Edit. |

**Two modes ignore the sidebar**: Edit and Animate. Both are instruction-driven and both already
have their subject fixed by a source image, so a sidebar that describes *a subject* has nothing to
contribute. Animate's box is worse than merely redundant without this — the sidebar's **Pose** value
is a *static* pose, which contradicts a motion instruction outright. `activePrompt()` is the single
place that decides what a mode sends, and the sidebar preview reads through it too; it used to render
`buildPrompt()` unconditionally and so claimed the sidebar text was in play during an Edit, which was
never true.

Gallery tiles and result cards both hang their actions off a **"⋯" hover menu** — Download, Refine,
Edit, Animate, Delete — so any output can be sent straight into any of the three modes. Refine/Edit/
Animate are suppressed on video results (`isVideo`), which is also why nothing offers to animate a
video. Opening the image itself is just a click on the thumbnail or card.

The menu is **one element**, `#item-menu`, lifted to `<body>` and `position: fixed`. It has to live
outside the tile for two reasons: the gallery scroller clips overflow, and virtualisation destroys
tiles on scroll, which would take an anchored menu with them. `openItemMenu()` measures after
showing (offsets are 0 while `display: none`), right-aligns to the trigger, and flips above it when
there's no room below. It closes on outside click, Escape, gallery/output scroll, and resize —
`position: fixed` against a button that scrolls away underneath it would otherwise drift.

*(Classic page — the new page uses escaped `data-` attributes and delegated listeners instead;
see The pytincture page.)* Menu items were built with **DOM calls and closures, not an innerHTML string**. The old inline
`onclick="setRefineFromGallery('${safeName}', …)"` handlers needed hand-rolled quote escaping to
survive a filename with an apostrophe in it; passing the name through a closure removes that class
of bug outright. `galleryTile()` and `showOutputs()` are built the same way for the same reason —
neither needs a `safeName`/`safeUrl` any more.

`deleteOutput()`'s `btn` argument is now optional: a call from the menu has no lasting button to
disable, because the menu closes before the confirm opens.

**Animate** is the video mode; `run.py video` reaches the same builders from the CLI
(`--image` for image→video, omit it for text→video).

**Prompt composition** (`buildPrompt()`) joins fields in a fixed order, manual text first:
manual prompt (`f-extra`) → expression → `eyes eyes` → `wearing X` → setting → lighting → style →
camera → pose → focus. In Person mode the whole thing is prefixed with `img `.

**Setting values carry their own preposition** (`on a beach`, `by a lake`, `aboard a spaceship`)
and are pushed verbatim. `buildPrompt()` used to prepend a blanket `in `, which emitted
`in beach` / `in pool`; per-value prepositions fix that and let each place pick the right word.
Clothing still uses a prepended `wearing `, because that one reads correctly for every value.

The manual box leads deliberately: diffusion models weight early tokens more heavily, so the text
you wrote should outrank the canned modifiers. (It used to be appended *last*, back when the
dropdowns carried the subject.)

That order is fixed in code and is **independent of the sidebar's visual order** — reordering the
markup does not reorder the prompt.

The prompt box and the preview share a `.prompt-sticky` wrapper (`position: sticky`) so both stay
pinned while the modifier dropdowns scroll under them. Its `top: -14px` / `padding-top: 14px` pair
cancels `.sidebar-inner`'s padding so the block lands flush when pinned, and the negative side
margins bleed its background to the rail edges — without them the scrolling selects show through
the gutters. Both halves are height-capped (`34vh` textarea, `16vh` preview) so the pinned block
can never grow over the whole rail.

**State** persists to `localStorage` under key `studio_v1` — prompt fields, mode, and
per-mode generation settings.

**Saved prompts** (the row under the Prompt heading): a picker that loads on selection, **Save**
(asks for a name — re-using a name overwrites, after a confirm) and **✕** (delete). A saved
prompt is `SAVED_PROMPT_FIELDS` = the sidebar's `PROMPT_FIELDS` (manual text + nine modifiers)
plus `neg-prompt` — deliberately **not** the checkpoint, LoRAs or sampler numbers, which belong
to a mode; reloading a prompt must not swap the model. Loading over a non-empty, different
sidebar asks first, and a saved dropdown value that no longer exists falls back to `—`.
They live **server-side** in `data/saved-prompts.json` (atomic write, a lock around
read-modify-write), not in `localStorage`, so they survive a cleared browser and a container
rebuild and are the same in every browser. The server bounds sizes (name ≤ 80, value ≤ 4000,
≤ 40 fields) but leaves which field ids exist to the page.

**Gallery** — collapsed it is just a header strip under the output area. Open, it *takes over the
display area*: `.gallery-section` gets `flex: 1` and `.output-area` is hidden (via a
`gallery-open` class on `.workspace` — the output area is an earlier sibling, so no CSS
combinator reaches it), giving the grid the workspace's full width and height. Tiles wrap into
rows and the panel scrolls vertically.

It is **virtualised**: `galleryItems` holds the whole file list and only the rows in view are
built as elements, so a few thousand outputs cost the same as a few dozen. `renderGalleryWindow()`
derives columns from the panel's width, sizes `#gallery-sizer` to the height every row *would*
occupy (that's what makes the native scrollbar correct), and `translateY`s `#gallery-inner` to the
first rendered row. Scroll and resize both re-render, coalesced to one per frame via `rAF`.

Two things to respect when touching it:

- **Tile geometry lives in CSS custom properties** (`--gtile`, `--gthumb`, `--gitem-h`, `--ggap`)
  and `galleryMetrics()` reads them back, so restyling tiles keeps the row math correct. But the
  tiles must stay *hard-sized* to those values — a tile that sizes to its content breaks the
  scroller, which is why `.gname` carries an explicit height. `--gitem-h` is `--gthumb + 4 + 14`:
  thumbnail, gap, filename. There is no button row to account for, since actions moved to the
  hover menu.
- **The DOM is not the list.** Anything that adds or removes an image must go through
  `galleryItems` and re-render; counting `.gallery-item` elements now only counts what's on screen.

Opening the gallery hides the output area, so `closeGallery()` runs from `generate()` and from the
`set*FromGallery()` pickers — otherwise a job's progress, or the controls a pick just filled in,
would be generated behind a covering panel.

**Deleting** — result cards and gallery tiles both carry a delete control (`Delete` / `✕`) calling
`deleteOutput()`, which confirms, hits `DELETE /outputs/{name}`, then drops **every** element whose
`data-file` matches. That matters because one image can be on screen twice at once (result column
*and* gallery); tagging both containers with `data-file` is what keeps them from going out of sync.
It then filters the name out of `galleryItems`, takes the count from *that*, and re-renders —
removing a tile shifts every later one into a new grid slot.

**Checkpoint dropdown** is populated live from `Studio.checkpoints()` (BFF), which proxies
ComfyUI's `object_info/CheckpointLoaderSimple`. Filenames are prettified for display by `ckptLabel()` and
grouped into one `<optgroup>` per base (FLUX / SDXL / SD 1.5, `BASE_ORDER`). A base with nothing
installed is skipped rather than rendered empty. FLUX GGUFs from `object_info/UnetLoaderGGUF`
are appended to the same list (base `FLUX`, Kontext excluded) — see FLUX below.

Because that list arrives *after* `loadState()` runs, the checkpoint selects need care that the
other fields don't — they hold only a `Loading…` placeholder when state is restored, so
`select.value = saved` silently no-ops. Two things keep the last-used model sticky:

- `loadState()` stashes the parsed blob in **`savedState`**, and `loadCheckpoints()` restores from
  *that*, not from the select's (still empty) live value.
- `saveState()` refuses to write an empty value over a real saved choice for the ids in
  **`ASYNC_SELECT_IDS`**. Without this the boot-time `updatePreview()` → `saveState()` call erases
  the saved checkpoint on every page load, before the fetch has even returned.

Any future control populated over the network needs both halves of that treatment.

**Per-checkpoint tuning is split in two** so a reload doesn't discard the user's own numbers:
`applyCheckpointUI()` does only the architecture-driven bits (CFG ↔ Guidance label, negative-prompt
visibility) and is safe to run on every boot; `applyCheckpointConfig()` additionally stamps the
recommended w/h/steps/CFG and is reserved for an explicit model change, or a first visit with
nothing saved. `loadCheckpoints()` picks between them by checking whether `savedState` holds that
mode's numeric fields.

## LoRAs

A checkpoint is the whole model — UNet, CLIP and VAE, loaded one at a time. A LoRA is a small
set of low-rank matrices merged into an existing checkpoint's attention layers at load time, so
it is never standalone and is tied to a base architecture (an SDXL LoRA will not load onto SD 1.5).

**`workflows/lora.py` rewrites a finished graph rather than being threaded through each builder.**
Every checkpoint-based builder publishes the same two edges — `["1", 0]` for MODEL and `["1", 1]`
for CLIP — so `lora.apply()` chains `LoraLoader` nodes off the checkpoint and repoints those
edges at the end of the chain. One function therefore covers `text2img`, `img2img`, `photomaker`
and both FLUX builders, including FLUX's `ModelSamplingFlux`, which sits between the checkpoint
and the sampler and is rewired like any other MODEL consumer. **Split graphs** (the GGUF FLUX
path: MODEL from `UnetLoaderGGUF` at `"1"`, CLIP from `DualCLIPLoader` at `"1c"`) pass
`clip_ref=["1c", 0]`; a `LoraLoader` takes its two inputs from two nodes just fine.

Two invariants that must survive any change here:

- **The rewrite runs before the chain is merged in.** The loaders' own `["1", 0]` / `["1", 1]`
  inputs must stay on the checkpoint — the first link is what anchors the chain. Merging first
  would rewrite them to point at themselves.
- **Slot 2 is never touched.** LoRAs do not patch the VAE, and `img2img` has two separate VAE
  consumers (`VAEEncode` and `VAEDecode`) that both have to keep reading the checkpoint.

Injected node ids are `lora_0`, `lora_1`, … — prefixed so they can never collide with a builder's
numeric ids.

**Edit and Animate have no LoRA support.** Kontext and WAN load a bare UNet via `UnetLoaderGGUF` /
`UNETLoader` with the text encoder coming from a separate node, so there is no single MODEL+CLIP
source to splice into; they would need `LoraLoaderModelOnly` wired by hand. `lora.apply()` raises
rather than guessing if it is pointed at such a graph, and the frontend hides the section in those
modes (`LORA_MODES`).

**The stack is a chain, not a set.** Entry N patches the model entry N−1 already patched, so order
is meaningful — the UI numbers the rows and offers move up/down rather than pretending otherwise.
Strength runs −1 to 2 (negative pushes away from the concept); one slider drives both
`strength_model` and `strength_clip`, which is what nearly every LoRA wants.

It rides to the server as a **JSON array on a single `loras` form field**, not repeated fields:
name and strength have to stay paired and ordered, and "second at 0.4" is meaningless once the
pairing is lost. The stack persists in `localStorage` under `__loras` alongside the id-keyed
fields, since the rows are dynamic and have no stable element ids.

A saved stack can outlive the files it names. Missing entries are **kept and flagged** in the UI
but filtered out of the payload by `activeLoras()` — dropping them silently would change the image
with no explanation, and sending them would fail the whole job.

Most LoRAs need a **trigger word** in the prompt to activate. Nothing in the app can know what it
is; that is on the LoRA's model card.

## Installed checkpoints

Live list from ComfyUI (10). "Kind" is what `workflows/defaults.py` infers from the filename:

| Checkpoint | Kind | Tuned defaults (`services/models.py`) |
|---|---|---|
| `sd_xl_base_1.0.safetensors` | SDXL | 1024², 25 steps, cfg 7 |
| `juggernautXL_ragnarokBy.safetensors` | SDXL | 1024², 35 steps, cfg 7 |
| `ponyDiffusionV6XL_v6StartWithThisOne.safetensors` | SDXL | 1024², 28 steps, cfg 7 |
| `dreamshaperXL_lightningDPMSDE.safetensors` | SDXL (lightning) | 1024², **6 steps, cfg 2** |
| `realvisxlV50_v50LightningBakedvae.safetensors` | SDXL (lightning) | 1024², **6 steps, cfg 2** |
| `crealismTerraMirabilis_v2025Steps.safetensors` | SDXL | 1024², 25 steps, cfg 7 |
| `talmendoxlSDXL_v11Beta.safetensors` | SDXL | *no entry* → falls back to the `xl` heuristic |
| `absolutereality_v181.safetensors` | SD 1.5 | 512², 25 steps, cfg 7 |
| `secuanceDreamDeliberate_v125Main.safetensors` | SD 1.5 | 512², 25 steps, cfg 7 |
| `v1-5-pruned-emaonly-fp16.safetensors` | SD 1.5 | 512², 20 steps, cfg 7 |

**FLUX text-to-image runs from a GGUF** (since 2026-10-27): `flux1-schnell-Q4_K_S.gguf`
(6.8 GB, `city96/FLUX.1-schnell-gguf`, Apache 2.0) in `models/unet/`. `flux.py` picks the
loader by filename: a `.gguf` loads split — `UnetLoaderGGUF` + `DualCLIPLoader`
(`clip_l` + `t5xxl_fp8_e4m3fn_scaled`, type `flux`) + `VAELoader` (`ae`), the same support
files as Kontext — and anything else as an all-in-one checkpoint via
`CheckpointLoaderSimple`. Both Generate and Refine take it, LoRAs included. Why GGUF: an fp8
all-in-one is ~12 GB of diffusion weights alone, the whole card. Measured with KoboldCPP
still loaded (9.5 GB): 1024² text2img in **24 s**, Refine in **16 s**, no OOM. Settings
come from the name (schnell → 4 steps / guidance 1.0; dev → 20 / 3.5). A dev GGUF works
the same way, but the dev repo is gated (`HF_TOKEN`) and non-commercial.

**Z-Image runs natively** (since 2026-11-03; Tongyi-MAI, Apache 2.0, ComfyUI's own support —
no custom node). Always a split load, so the files live outside `checkpoints/`:

| File | Goes in | From |
|---|---|---|
| `z_image_turbo_bf16.safetensors` (12.3 GB) and/or `z_image_bf16.safetensors` (12.3 GB) | `models/diffusion_models/` | `Comfy-Org/Z-Image-Turbo`, `Comfy-Org/Z-Image` (`split_files/…`) |
| `qwen_3_4b.safetensors` (8.0 GB) | `models/text_encoders/` | either repo |
| `ae.safetensors` | `models/vae/` | the FLUX VAE, already installed |

`workflows/zimage.py` follows ComfyUI's templates (`image_z_image_turbo` / `image_z_image`):
`UNETLoader` + `CLIPLoader` (`qwen_3_4b`, type `lumina2`) + `VAELoader` (`ae`),
`ModelSamplingAuraFlow` shift 3, `EmptySD3LatentImage`, `res_multistep` + `simple`.
**Turbo** (name contains `turbo`): 8 steps, CFG 1, negative hidden — at CFG 1 ComfyUI never
evaluates it, which is what the template's `ConditioningZeroOut` amounts to. **Base**: 25 steps,
CFG 4, negative used. Generate and Refine both take it, LoRAs included (node `"1"` MODEL, `"1c"`
CLIP, like the GGUF FLUX path; the shift node is rewired after the chain). The picker lists
`object_info/UNETLoader` names that `base_of()` calls Z-Image (`z[-_ ]?image`) — that folder
also holds WAN and ACE-Step, which must not appear. `config_for()` may return `neg: False`;
`_apply_ui` hides the negative box for it, as it always did for FLUX.

**Model-type detection has one home: `workflows/defaults.py`.** `is_zimage()` / `is_flux()` / `is_sdxl()`
(the `_SDXL_NAMES` keyword set) classify a filename, `base_of()` turns that into `"Z-Image"` /
`"FLUX"` / `"SDXL"` / `"SD 1.5"`, and `default_size()` builds on the same pair for `run.py`.

`/checkpoints` returns `[{name, base}]` rather than bare filenames, so the frontend groups the
picker and picks its config fallback from the server's answer instead of re-deriving one. This
used to live in two places — the backend keyword set, and an `xl` substring test in the frontend —
which disagreed about `crealismTerraMirabilis` (SDXL, no "xl" in the name) and meant every new
checkpoint had to be taught to both. Now a new checkpoint only needs `_SDXL_NAMES`, if anything.

`checkpointBase` in the frontend is a cache of that response; `_baseOf()` falls back to substring
tests only for the window before `/checkpoints` has answered.

Adding a **new base family** means (Z-Image is the worked example): teach `defaults.py` to detect
it, add it to `BASES`, a builder under `workflows/` that `text2img`/`img2img` delegate to, a
`config_for()` branch, the loader listing in `server.list_checkpoints()` if it isn't a checkpoint,
and add it to `BASE_ORDER` in `appcode/ui/panels.py` — the picker appends unknown bases after the known ones rather
than dropping them, so a missed `BASE_ORDER` entry degrades to bad ordering, not a missing group.

## Flux Kontext (Edit mode) — how it's wired

Working as of 2026-08-11; verified end-to-end through the GUI API.

**What it is.** Instruction-driven editing. Refine (img2img) re-noises the whole image and hopes;
Kontext encodes the source to a latent and binds it to the *conditioning* via `ReferenceLatent`, so
the model treats the picture as context and the prompt as an instruction. Everything you don't
mention is preserved — verified: "change the background to a snowy mountain landscape" swapped the
backdrop while leaving face, glasses, beard and shirt pixel-identical.

**Prompt like an instruction, not a description.** `"make him wear a red baseball cap"` works;
`"a man in a red cap, 8k, detailed"` makes it redraw the picture. Edit mode therefore takes its
prompt from **its own instruction box** and ignores the prompt sidebar entirely — that
sidebar composes descriptions, which is the wrong shape of text for this model.

**Models** (~12.5 GB, none of it in git):

| File | Goes in | From |
|---|---|---|
| `flux1-kontext-dev-Q4_K_M.gguf` (6.9 GB) | `models/unet/` | `QuantStack/FLUX.1-Kontext-dev-GGUF` |
| `t5xxl_fp8_e4m3fn_scaled.safetensors` (4.9 GB) | `models/text_encoders/` | `comfyanonymous/flux_text_encoders` |
| `clip_l.safetensors` (235 MB) | `models/text_encoders/` | `comfyanonymous/flux_text_encoders` |
| `ae.safetensors` (320 MB) | `models/vae/` | `Comfy-Org/Lumina_Image_2.0_Repackaged` |

**GGUF is not a preference, it's the only option.** Every tutorial uses
`flux1-dev-kontext_fp8_scaled.safetensors`, which needs **~20 GB VRAM**. This card has 12. Hence
the Q4_K_M quant and the **ComfyUI-GGUF** custom node (city96) for `UnetLoaderGGUF`; its `gguf` dep
is baked into `ai-stack/comfyui/Containerfile` like every other custom-node dep. Q5_K_M (8.4 GB)
would also fit but leaves little headroom; Q6_K and above will thrash.

**Graph** (`workflows/kontext.py`) mirrors ComfyUI's own bundled `flux_kontext_dev_basic` template
with `UNETLoader` swapped for `UnetLoaderGGUF`. Three things about it are easy to get wrong:
- **`FluxKontextImageScale` is mandatory.** It snaps the source to a trained resolution; skipping it
  is the most common cause of mushy or warped output.
- **Sampler CFG is pinned to 1.0** — Kontext is guidance-distilled. The real knob is `FluxGuidance`
  (2.5 default, ~1.5 subtle, ~4 forceful). The GUI's slider sends it in the **`cfg` form field** to
  reuse the existing plumbing, so `cfg` means *guidance* for this task and nothing else.
- **No negative prompt and no denoise.** The negative is a `ConditioningZeroOut` of the positive,
  and sampling always runs at denoise 1.0 because the source arrives via `ReferenceLatent` rather
  than as a partially-noised latent.

**~75 s per 1024² edit** at 20 steps on the 4070.

### The VRAM conflict — it bites in both directions

Kontext needs ~7 GB; KoboldCPP holds ~5.9 GB. **They cannot both be loaded on a 12 GB card.**

- Before editing: `stack down koboldcpp`, or the job OOMs / offloads to system RAM and crawls.
- **After editing, ComfyUI keeps the model resident** (~6.4 GB observed). KoboldCPP then dies
  *instantly* on restart, and because `start.sh` runs it with `--rm` the container vanishes before
  it can log anything — `stack up` just reports "did not come up" and `podman logs` says no such
  container. It looks like a broken KoboldCPP; it's actually an out-of-memory GPU.

The fix is to make ComfyUI let go, which it will do on request without a restart:
```bash
curl -X POST http://localhost:8188/free -H 'Content-Type: application/json' \
     -d '{"unload_models":true,"free_memory":true}'
```
That reliably returns ~6 GB, after which KoboldCPP starts normally. This is deliberately **not**
automated — a frontend silently stopping or unloading another service is surprising behaviour.

## PhotoMaker (Person mode) — how it's wired

Working as of 2026-08-10; verified end-to-end with PhotoMaker V2 and two reference photos.

**Custom node.** `ComfyUI-PhotoMaker-Plus` (shiimizu), cloned into
`~/Development/ai_ecosystem/ComfyUI/custom_nodes/ComfyUI-PhotoMaker-Plus`
(pinned at `459f5c0`, 2024-12-01). It supplies `PhotoMakerLoaderPlus`,
`PhotoMakerEncodePlus`, `PhotoMakerLoraLoaderPlus`, `PhotoMakerInsightFaceLoader`,
and `PhotoMakerStyles`. ComfyUI's *built-in* `PhotoMakerLoader` / `PhotoMakerEncode` are a
different, weaker pair — they have no InsightFace path, so **V2 needs the custom node**.
V1 vs V2 is auto-detected by the loader from the checkpoint's keys, not from the filename.

**Python deps live in the image, not the node.** Custom nodes are bind-mounted state, but their
dependencies have to be baked into the ComfyUI image or they disappear every time the container
is recreated (`start.sh` does `podman rm -f`). They're installed in
`ai-stack/comfyui/Containerfile`: `insightface==1.0.1` + `onnxruntime==1.28.0`.

Two deliberate deviations from the node's own `requirements.txt` — **do not "fix" these**:
- It pins **`numpy<2`**, needed only for the ancient insightface 0.7.3 sdist. Honouring it would
  downgrade numpy under torch 2.11 / ComfyUI 0.31 and break the image. insightface **1.0.1**
  ships a pure-Python wheel (no compiler — this image has no gcc) and works fine on numpy 2.4.
- It asks for **`onnxruntime-gpu`**. We install the CPU build: there's no onnxruntime-gpu wheel
  matching this image's CUDA 13 torch, and it would pull a conflicting CUDA runtime. Face
  detection is one ~0.3 s pass per job on the small buffalo_l model — irrelevant next to the
  diffusion. `INSIGHTFACE_PROVIDER = "CPU"` in `workflows/photomaker.py` matches this.

**InsightFace models.** `models/insightface/models/buffalo_l/` (5 `.onnx` files) — that exact
nesting matters, because the node calls `FaceAnalysis(name="buffalo_l", root=<models>/insightface)`
and insightface then looks in `root/models/<name>/`. The stray `models/insightface/buffalo_1/`
directory is an unused misnamed copy.

**Behaviour note.** With studio-headshot references, V2's identity conditioning is strong enough to
override scene/wardrobe terms in the prompt. If the background or clothing is being ignored, that's
PhotoMaker working as designed, not a bug — lower the influence by using more varied reference
photos, or describe the scene more emphatically.

## Known broken / stale

**1. `run.py` CLI is thinner than the GUI.** `text2img`/`img2img` take `--checkpoint`, and size
defaults to the checkpoint's native resolution via `defaults.default_size()` — so FLUX is reachable
from the CLI too (any name containing `flux` switches workflow). Still missing: no `photomaker`
subcommand, and none of the GUI's per-checkpoint step/CFG tuning, so lightning models need an
explicit `--steps 6 --cfg 2`.

**2. Jobs are in-memory only.** `JOBS` in `services/jobs.py` has no eviction and no persistence:
it grows for the process lifetime and every job is lost on restart. This bites harder since Animate
landed — losing a 3 s still is nothing, losing a several-minute video job is not.

## Video — WAN 2.2 TI2V 5B (Animate)

`workflows/video.py` replaced an AnimateDiff module that had never run: it targeted `ADE_*` and
`VHS_*` nodes from two custom node packs, neither installed. **None of that is needed.** ComfyUI
v0.31.1 ships native WAN support, so this feature costs **zero custom nodes, zero `stack`
`CUSTOM_NODES` rows and zero image rebuilds** — only the weights in `ai-stack/comfyui/INSTALL.md` §8.

- **One graph, two entry points.** `Wan22ImageToVideoLatent` takes `start_image` as an *optional*
  input, so image→video and text→video differ by exactly one key. `build_i2v` and `build_t2v` share
  `_build`, which is what stops the GUI's sampler settings drifting from the CLI's.
- **`length` must be 4n+1** — the 5B VAE compresses 4× temporally, and an off-grid length dies deep
  inside the sampler with a shape error that reads like a bug. `clamp_length()` rounds *down* onto
  the grid within 5–121, so a request can never silently cost more time than it asked for. The GUI
  mirrors the same snap in `updateAnimateLength()` so the label can't promise a length the server
  rounds away.
- **1280×704 is native.** Going far under it degrades WAN the way 512² degrades SDXL. The Size
  control is a fixed select rather than free w/h boxes for exactly that reason.
- **`SaveVideo` reports its file under the `images` key**, not `videos`, and sets `"animated":
  [true]` alongside — a list of *booleans*. `client._collect_output_items` used to extend blindly
  from every key, so `download_outputs` died on `item["filename"]` **after** a multi-minute render
  had already succeeded. It now takes only dicts carrying a filename, and dedupes on
  (filename, subfolder, type) so a file reported under two keys isn't fetched twice and rendered as
  two cards.
- **Video jobs get `VIDEO_TIMEOUT` (1800 s)**, not the 600 s default. A long clip that finished but
  got reported as a timeout burns the GPU time and throws the result away.
- **`COMFY_BASE` is gone.** It existed only to feed the old AnimateDiff pre-flight file check.
- **VRAM: WAN 5B wants the card to itself.** fp16 is ~10 GB of the 11.6 GiB total. `stack down
  koboldcpp` (or stack-ui's `POST /api/vram/free`) first. If it still won't fit, drop a GGUF WAN 5B
  into `models/unet/` and swap node `1` from `UNETLoader` to `UnetLoaderGGUF` — `ComfyUI-GGUF` is
  already installed for Flux Kontext and nothing else in the graph changes.

### Why the defaults are what they are

Both were set by measurement after the model looked like it was ignoring motion prompts. Fixed seed,
fixed source, prompt "she raises her right hand and touches her own shoulder":

| length | negative | mean frame-to-frame motion | outcome |
|---|---|---|---|
| 49 | old | 2.01 | hand ends at the ribs |
| 49 | new | 2.07 | incomplete |
| 81 | old | 4.05 | near miss — hands to chest |
| 81 | new | **5.20** | **hand lands on the shoulder** |

- **`DEFAULT_LENGTH` is 81, not 49.** ~2 s is not enough room for the model to *finish* an ordinary
  action: it begins the reach and the clip ends. Both 49-frame runs failed regardless of the
  negative; both 81-frame runs produced the full arm movement. **Length is the dominant factor** —
  a short default made the model look like it was ignoring the prompt when it was running out of time.
- **`NEGATIVE_VIDEO` no longer suppresses motion.** It inherited `abrupt motion`, `jitter`,
  `flickering` and `strobing` from the AnimateDiff module, aimed at *that* model's temporal
  artifacts. Under WAN at CFG 5 they also push away from deliberate movement — raising an arm is
  "abrupt motion" next to ambient drift. Worth ~25% more motion, and the difference between landing
  the shoulder and drifting to the chest. The anti-motion intent survives as `static, still frame,
  frozen, motionless`, which *ask* for movement rather than forbidding it.
- **Framing is on the operator.** A tight head-and-shoulders crop has no arm in frame, so there is
  nowhere for a hand to come from. No setting fixes that.

Measured on this box: 25 frames at 960×544, 20 steps → **41 s**; 81 frames at 544×960, 30 steps →
**175 s** end to end.

## Live progress + ETA

"Running…" is adequate for a 4-second still and useless for a 3-minute video, where the
only question is whether it is 40% done or hung. `jobs.view()` carries `phase`,
`progress {value, max}` and `eta`; the page receives it over `Studio.follow()` (streamed,
not polled since the pytincture switch-over) and renders a bar beside the spinner.

- **The websocket is the only source.** `/api/jobs/{id}` (new in v0.31.1) reports a status
  and a duration but no step counter, and there is no REST progress route — checked. So
  `client._watch_progress` opens `ws://…/ws?clientId=…` and ComfyUI's `progress` messages
  carry `{value, max, prompt_id, node}`. That is the one new dependency:
  `websocket-client`, sync by design because jobs already run in threads.
- **The socket is opened *before* the job is queued.** Connecting after races the first
  messages, and on a short job the bar then never moves at all.
- **The client_id must match.** ComfyUI addresses progress to the client that submitted
  the job, so `queue_prompt` takes one and the websocket is opened with the same value.
- **A dead socket must never re-queue.** If the stream drops mid-job the render is still
  going on the other side, so `_watch_progress` hands the prompt_id back and the caller
  polls for it. Re-queueing there would silently render a multi-minute video twice — which
  is also why the caller's `on_progress` is wrapped: a throwing callback would look
  exactly like a dead socket.
- **Progress is a nicety, the render is the point.** Anything that fails before the job is
  queued falls back to the old queue-and-poll path with no progress, rather than failing a
  job that would have succeeded.
- **The ETA is measured, not modelled** — elapsed-per-completed-step over the steps left.
  No calibration constant, so nothing goes stale when the model, precision or driver
  changes, and it corrects itself as the run proceeds.
- **It anchors on the first step *seen*, and stores that step number.** ComfyUI throttles
  `progress` messages, so the first one can already say "step 18"; anchoring on time alone
  divides a near-zero elapsed by 18 and reports `0s` remaining for the whole run. Observed
  exactly that before the fix. No ETA is shown until a second step arrives — one sample
  gives no rate, and a made-up number is worse than none.
- **The bar covers sampling, not the whole job.** The model load lands before the first
  step and the VAE decode plus mp4 mux after the last, so the phase is shown next to the
  bar rather than letting the step count imply the whole run. `PHASES` maps class_type →
  label, so it works for every task without each builder describing itself.
- `updateJobStatus()` rewrites text and bar **in place**: replacing the card restarts the
  CSS spinner animation, which reads as the job having started over.

Measured: img2vid 960×544, L=25, 30 steps → ETA said 35 s at step 3, sampling ended 4 s
later, 55 s total including decode and mux.

## API endpoints
| Method | Path | Purpose |
|---|---|---|
Plain HTTP (everything else is BFF — `/iguana/bff-docs` lists those):

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Redirects to `/iguana/`, the page |
| GET | `/api/health` | `{"ok": true}` — `stack status`, the container HEALTHCHECK |
| POST | `/upload` | Multipart `files` → `{"ids": [...]}` in `temp/`; ≤ 40 MB each, images only |
| GET | `/outputs/{filename}` | Serves one generated file |
| GET | `/thumbs/{filename}?v=<mtime>` | Gallery tile: 280 px WebP of an output image, cached in `outputs/.thumbs/`; immutable-cacheable with `v` |
| GET | `/debug/nodes` | Every node class ComfyUI knows — useful for the breakage above |
| POST | `/debug/workflow` | Dry-run a graph and return the JSON without queueing |

BFF: `Studio` (`checkpoints`, `loras`, `comfy_status`, `generate(task, fields, upload_ids)`,
`from_output`, `job`, `follow` — the stream), `Prompts` (`all`, `save`, `delete`), `Gallery`
(`items`, `delete`). `generate()` coerces numbers itself (no `Form()` anymore).

## Key design decisions
- **The page streams; `client.py` uses a websocket.** The page follows a job over
  `Studio.follow()` (a BFF stream that reconnects by job id, so it also survives a reload).
  Toward ComfyUI it is a websocket, because step-level progress is exposed nowhere else, with
  the `/history` polling loop kept as the fallback when the socket can't be had.
- **Threading** — each generation runs in a `daemon=True` thread; no queue, no worker pool.
- **No JS build step** — the page is Python modules under `appcode/` that pytincture ships to
  Pyodide, plus one stylesheet.
- **Path traversal protection** — `GET /outputs/{filename}` and `server.delete_output()` apply
  `Path(filename).name` to strip any directory part. Delete additionally refuses anything outside
  `MEDIA_SUFFIXES`, the same set `server.gallery()` lists by. Uploads are named by the server
  (`up-<hex>.<ext>`); the BFF only accepts ids matching that pattern, and `from_output()` only
  basenames of images already in `outputs/`.
- **Uploads are ephemeral** — temp files are unlinked in the job's `finally` block.
- **Per-model defaults are a UX affordance, not a constraint** — switching checkpoint overwrites
  the steps/cfg/resolution boxes, and for FLUX relabels CFG → Guidance and hides the negative
  prompt (FLUX bakes guidance into `CLIPTextEncodeFlux`).

## Workflow graph format (ComfyUI API format)
Each workflow is a dict of `{"node_id": {"class_type": ..., "inputs": {...}}}`; node outputs are
referenced as `["node_id", output_index]`.
- `CheckpointLoaderSimple` → `[0]=model, [1]=clip, [2]=vae`
- `KSampler` → `[0]=latent` · `VAEDecode` → `[0]=image`
- SDXL uses `CLIPTextEncodeSDXL` (dual `text_g`/`text_l`); SD 1.5 uses plain `CLIPTextEncode`
- FLUX uses `CLIPTextEncodeFlux` + `ModelSamplingFlux` + `EmptySD3LatentImage`, cfg pinned to 1.0
- `photomaker.py` builds node IDs **dynamically** (one `LoadImage` per reference photo, chained
  through `ImageBatch`), so IDs shift with the number of uploads — the only non-static graph here
- `LoraLoader` → `[0]=model, [1]=clip`; it consumes MODEL+CLIP and hands back patched ones
