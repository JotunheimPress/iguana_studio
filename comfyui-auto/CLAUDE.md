# Iguana Studio (comfyui-auto) — Project Context

## What this is
A Python toolkit + single-page web GUI that drives ComfyUI over its HTTP API.
No clicking around in ComfyUI's node editor — the GUI composes a prompt from structured
character fields, submits a generated workflow graph, polls for the result, and saves it.

Facts below were verified against the running stack on **2026-08-10**. Where the code and
reality disagree, that's called out explicitly under [Known broken / stale](#known-broken--stale).

## Runtime topology

| Piece | Where | Reached at |
|---|---|---|
| **iguana GUI** | Podman container `iguana` on network `ai-net` | host `http://localhost:7862` |
| **ComfyUI** | Podman container `comfyui` on network `ai-net` | `comfyui:8188` (from inside `ai-net`) |
| ComfyUI data | bind mounts from `~/Development/ai_ecosystem/ComfyUI/` | `/data/{models,custom_nodes,input,output,user}` |
| `outputs/` | bind mount from the repo dir | `/app/outputs` |

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

**Host dev (venv)** — for the CLI, or to iterate without rebuilding the image:
```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt
PORT=7862 venv/bin/python server.py        # GUI → http://localhost:7862
venv/bin/python run.py text2img "a cat"    # CLI (see caveats below)
```

### Environment variables
| Var | Default (container) | Purpose |
|---|---|---|
| `COMFY_HOST` | `comfyui` | ComfyUI hostname |
| `COMFY_PORT` | `8188` | ComfyUI port |
| `PORT` | `7862` | Port the GUI binds |
| `COMFY_BASE` | *unset in container* | Host path to the ComfyUI folder. Only used for the video tab's client-side pre-flight file check; skipped when the path isn't visible (`server.py:52`). |

The startup banner derives its printed URL from the same `PORT` value it binds, so the two can't
drift apart. (It used to hardcode 7861 — the **companion** app's port; iguana is 7862.)

## Project structure
```
comfyui-auto/
├── server.py            # FastAPI web GUI — the main entry point
├── run.py               # CLI alternative (text2img / img2img / video only)
├── client.py            # ComfyUI API client: queue, poll /history, download /view
├── workflows/
│   ├── defaults.py      # shared negative prompts + is_flux() / is_sdxl() detection
│   ├── text2img.py      # text → image; delegates to flux.py when checkpoint is FLUX
│   ├── img2img.py       # edit an image; also delegates to flux.py
│   ├── flux.py          # FLUX.1 graphs (build + build_img2img)
│   ├── photomaker.py    # person from reference photos  ← see Known broken
│   └── video.py         # AnimateDiff text → video      ← see Known broken
├── static/index.html    # entire frontend, ~1500 lines, no build step
├── outputs/             # generated files (volume-mounted, gitignored)
├── temp/                # uploaded images, deleted after each job
├── Containerfile        # python:3.12-slim + requirements, HEALTHCHECK on /
└── run-podman.sh        # build + run on ai-net
```

## The GUI

A left rail of **character-builder dropdowns** feeds a prompt composer; a right panel holds
mode-specific generation controls; below sits the output view and a gallery.

**The app is named "Iguana Studio"** (it was generically "Character Studio" until 2026-08-11). The
name is written out in three places that must be changed together: `<title>` and the topbar `<h1>`
in `static/index.html`, and `FastAPI(title=...)` in `server.py` (which surfaces at `/docs`). The
`<h1>` deliberately keeps the second word in a `<span>` — `.topbar h1 span` renders it muted
against the accented first word, so any rename should stay two words to preserve that.
Unrelated: "Character" in the sidebar still labels the character-builder panel — that's a feature
name, not branding, and the `localStorage` key stays `studio_v1` (renaming it discards saved state).

**Three modes** (`static/index.html:811`), which map onto backend tasks:

| Mode | Task sent | Controls | Notes |
|---|---|---|---|
| **Generate** | `text2img` | checkpoint, w/h, steps, cfg, seed, negative | The main path. Works. |
| **Person** | `photomaker` | PhotoMaker model, w/h, steps, cfg, multi-photo dropzone | Prepends trigger word `img`. Needs the PhotoMaker-Plus custom node — see below. |
| **Refine** | `img2img` | checkpoint, denoise slider, steps, cfg, seed, source image | Source can be uploaded or picked from the gallery. |

There is **no video mode in the GUI**. The `video` task is only reachable via `run.py video`
or a hand-rolled `POST /generate`.

**Prompt composition** (`buildPrompt()`, `index.html:1020`) joins fields in a fixed order:
`expression age gender` → `build, skin skin` / `haircolor hairstyle hair` / `eyes eyes` →
`wearing X` → `in X` → lighting → style → camera → pose → focus → free-text extra.
In Person mode the whole thing is prefixed with `img `.

**State** persists to `localStorage` under key `studio_v1` — character fields, mode, and
per-mode generation settings.

**Deleting** — result cards and gallery tiles both carry a delete control (`Delete` / `✕`) calling
`deleteOutput()`, which confirms, hits `DELETE /outputs/{name}`, then drops **every** element whose
`data-file` matches. That matters because one image can be on screen twice at once (result column
*and* gallery); tagging both containers with `data-file` is what keeps them from going out of sync.
The gallery count is recomputed from the surviving tiles rather than refetched — `loadGallery()`
runs at page load, so the tiles exist in the DOM even while the panel is collapsed.

**Checkpoint dropdown** is populated live from `/checkpoints`, which proxies ComfyUI's
`object_info/CheckpointLoaderSimple`. Filenames are prettified for display by `ckptLabel()`.

## Installed checkpoints

Live list from ComfyUI (10). "Kind" is what `workflows/defaults.py` infers from the filename:

| Checkpoint | Kind | Tuned defaults (frontend) |
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

**No FLUX checkpoint is installed.** `flux.py` is complete and wired in, but only activates when
a checkpoint filename contains `flux`, so it is currently dead code. Drop a FLUX merged
checkpoint into `models/checkpoints/` and it lights up automatically (schnell → 4 steps /
guidance 1.0; dev → 20 steps / guidance 3.5, detected by `schnell` in the name).

**Model-type detection lives in two places and must be kept in sync:**
- backend — `workflows/defaults.py` `is_flux()` / `is_sdxl()` (the `_SDXL_NAMES` keyword set).
  `default_size()` builds on these and is what `run.py` uses to pick a resolution.
- frontend — `CKPT_CONFIGS` + the `xl` substring fallback (`index.html:1127`)

Adding a checkpoint whose name lacks `xl` means adding it to **both** lists.

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

**1. Video is not usable.** No `ADE_*` or `VHS_*` nodes are loaded, and
`models/animatediff_models/` is empty. To enable: install **ComfyUI-AnimateDiff-Evolved** and
**ComfyUI-VideoHelperSuite** into `custom_nodes/`, download `mm_sd_v15_v2.ckpt` into
`models/animatediff_models/`, restart ComfyUI — then add a GUI mode, since none exists.

**2. `run.py` CLI is thinner than the GUI.** `text2img`/`img2img` take `--checkpoint`, and size
defaults to the checkpoint's native resolution via `defaults.default_size()` — so FLUX is reachable
from the CLI too (any name containing `flux` switches workflow). Still missing: no `photomaker`
subcommand, and none of the GUI's per-checkpoint step/CFG tuning, so lightning models need an
explicit `--steps 6 --cfg 2`.

**3. Jobs are in-memory only.** `jobs: dict` in `server.py` has no eviction and no persistence:
it grows for the process lifetime and every job is lost on restart.

## API endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Serves the web GUI |
| GET | `/comfy-status` | `{"running": bool}` — polled by the status dot |
| POST | `/generate` | Multipart form; starts a job, returns `{"job_id": ...}` |
| GET | `/job/{id}` | `{status, files, message}`; status ∈ pending/running/done/error/not_found |
| GET | `/checkpoints` | Sorted checkpoint filenames from ComfyUI |
| GET | `/gallery` | All output files, newest first, with mtime + size |
| GET | `/outputs/{filename}` | Serves one generated file |
| DELETE | `/outputs/{filename}` | Deletes one generated file (no trash — it's gone) |
| GET | `/debug/nodes` | Every node class ComfyUI knows — useful for the breakage above |
| POST | `/debug/workflow` | Dry-run a graph and return the JSON without queueing |

## Key design decisions
- **Polling, not websockets** — the client polls `/job/{id}` every 2s; `client.py` polls ComfyUI's
  `/history/{prompt_id}` every 1.5s with a 600s timeout. Simpler and reliable.
- **Threading** — each generation runs in a `daemon=True` thread; no queue, no worker pool.
- **No build step** — the frontend is one self-contained HTML file with inline CSS/JS.
- **Path traversal protection** — both `/outputs/{filename}` routes apply `Path(filename).name` to
  strip any directory part. DELETE additionally refuses anything outside `MEDIA_SUFFIXES`, the same
  set `/gallery` lists by, so the two can't disagree about what's deletable.
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
