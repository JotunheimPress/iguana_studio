# Iguana Studio (comfyui-auto) — Project Context

## What this is
A Python toolkit + single-page web GUI that drives ComfyUI over its HTTP API.
No clicking around in ComfyUI's node editor — you write a prompt, the GUI submits a generated
workflow graph, polls for the result, and saves it.

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
│   ├── kontext.py       # Flux Kontext instruction editing (Edit mode)
│   └── video.py         # WAN 2.2 image→video + text→video
├── static/index.html    # entire frontend, ~1500 lines, no build step
├── outputs/             # generated files (volume-mounted, gitignored)
├── temp/                # uploaded images, deleted after each job
├── Containerfile        # python:3.12-slim + requirements, HEALTHCHECK on /
└── run-podman.sh        # build + run on ai-net
```

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
name is written out in three places that must be changed together: `<title>` and the topbar `<h1>`
in `static/index.html`, and `FastAPI(title=...)` in `server.py` (which surfaces at `/docs`). The
`<h1>` deliberately keeps the second word in a `<span>` — `.topbar h1 span` renders it muted
against the accented first word, so any rename should stay two words to preserve that.
The `localStorage` key stays `studio_v1` (renaming it discards saved state) — dropping fields from
`PERSIST_IDS` is enough, since stale keys in a saved blob are simply ignored on load.

**Four modes** (`static/index.html:838`), which map onto backend tasks:

| Mode | Task sent | Controls | Notes |
|---|---|---|---|
| **Generate** | `text2img` | checkpoint, w/h, steps, cfg, seed, negative | The main path. Works. |
| **Person** | `photomaker` | PhotoMaker model, w/h, steps, cfg, multi-photo dropzone | Prepends trigger word `img`. Needs the PhotoMaker-Plus custom node — see below. |
| **Refine** | `img2img` | checkpoint, denoise slider, steps, cfg, seed, source image | Source can be uploaded or picked from the gallery. |
| **Edit** | `kontext` | instruction box, guidance slider, steps, seed, source image | Flux Kontext instruction editing — see below. **Ignores the prompt sidebar.** |
| **Animate** | `img2vid` | source image, length, fps, size, steps, CFG, shift, seed | WAN 2.2 image→video — see below. The prompt describes the *motion*; the subject is already fixed by the image. |

Gallery tiles and result cards carry **Refine**, **Edit** and **Animate** buttons, so any output can
be sent straight into any of the three. All three are suppressed on video results (`isVideo`), which
is also why nothing offers to animate a video.

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
- frontend — `CKPT_CONFIGS` + the `xl` substring fallback (`index.html:1154`)

Adding a checkpoint whose name lacks `xl` means adding it to **both** lists.

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

**2. Jobs are in-memory only.** `jobs: dict` in `server.py` has no eviction and no persistence:
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

Measured on this box: 25 frames at 960×544, 20 steps → **41 s**.

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
