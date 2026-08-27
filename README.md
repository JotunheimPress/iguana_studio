# Iguana Studio

A prompt-first web GUI for [ComfyUI](https://github.com/comfyanonymous/ComfyUI). You type a
prompt, pick a mode, and press Generate — Iguana Studio builds the ComfyUI workflow graph,
submits it over the HTTP API, polls for the result, and drops it in a gallery. No node editor,
no wiring, no build step.

It's a small FastAPI service plus one self-contained HTML page, designed to sit next to a running
ComfyUI instance on the same container network.

## Modes

| Mode | What it does |
|---|---|
| **Generate** | Text → image. The main path. Per-checkpoint defaults for size, steps and CFG. |
| **Person** | Identity-preserving portraits from reference photos, via PhotoMaker V2. |
| **Refine** | img2img — re-noise an existing image with a denoise slider. |
| **Edit** | Instruction-driven editing with Flux Kontext ("change the background to a snowy mountain"). Everything you don't mention is preserved. |

Any generated image carries **Refine** and **Edit** buttons, so an output can be fed straight back
into either editing path.

The sidebar is prompt-first: you write the subject in free text, and the dropdowns (Art style,
Setting, Lighting, Camera, Clothing, Pose, Focus, Expression, Eye colour) only *append* modifiers.
Every one defaults to off, so a fresh session generates exactly what you typed. The composed
prompt is shown live in a pinned preview above the modifiers.

State — prompt fields, mode, per-mode generation settings — persists in `localStorage`.

## Requirements

- A running **ComfyUI** instance, reachable over HTTP.
- Python 3.12+ (host dev) or Podman/Docker (containerized).
- Checkpoints installed in ComfyUI's `models/checkpoints/`. SD 1.5, SDXL and FLUX graphs are all
  supported and selected automatically from the checkpoint filename.
- **Edit mode** additionally needs the [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF)
  custom node plus a Flux Kontext GGUF unet, T5/CLIP text encoders and a VAE (~12.5 GB).
- **Person mode** additionally needs
  [ComfyUI-PhotoMaker-Plus](https://github.com/shiimizu/ComfyUI-PhotoMaker-Plus), a PhotoMaker
  checkpoint, and InsightFace `buffalo_l` models.

See `comfyui-auto/CLAUDE.md` for the exact model files and paths.

## Running it

### Container (recommended)

```bash
cd comfyui-auto
./run-podman.sh                # builds on first run, then starts on :7862
./run-podman.sh --rebuild      # rebuild the image
./run-podman.sh --port 8862    # bind a different host port
```

The container joins the `ai-net` Podman network and reaches ComfyUI at `comfyui:8188`. That
network membership is required, not optional — the hostname only resolves there.

```bash
open http://localhost:7862
podman logs -f iguana
podman rm -f iguana
```

### Host (venv)

Useful for the CLI, or for iterating on the frontend without rebuilding an image.

```bash
cd comfyui-auto
python3 -m venv venv && venv/bin/pip install -r requirements.txt
COMFY_HOST=localhost PORT=7862 venv/bin/python server.py
```

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `COMFY_HOST` | `comfyui` | ComfyUI hostname |
| `COMFY_PORT` | `8188` | ComfyUI port |
| `PORT` | `7862` | Port the GUI binds |
| `COMFY_BASE` | *unset* | Host path to the ComfyUI folder; only used for a client-side pre-flight file check, skipped when the path isn't visible |

## CLI

`run.py` is a thinner alternative to the GUI — `text2img`, `img2img` and `video` only, with no
PhotoMaker subcommand and none of the GUI's per-checkpoint tuning.

```bash
venv/bin/python run.py text2img "a cat on a windowsill, 35mm film photography"
venv/bin/python run.py img2img photo.png "make it snow" --denoise 0.55
```

Resolution defaults to the checkpoint's native size. Lightning checkpoints need their settings
passed explicitly: `--steps 6 --cfg 2`.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | The web GUI |
| `GET` | `/comfy-status` | `{"running": bool}` — polled by the status dot |
| `POST` | `/generate` | Multipart form; starts a job, returns `{"job_id": ...}` |
| `GET` | `/job/{id}` | `{status, files, message}` — pending / running / done / error / not_found |
| `GET` | `/checkpoints` | Checkpoint filenames from ComfyUI, sorted |
| `GET` | `/gallery` | All outputs, newest first, with mtime and size |
| `GET` | `/outputs/{filename}` | Serve one generated file |
| `DELETE` | `/outputs/{filename}` | Delete one generated file (no trash — it's gone) |
| `GET` | `/debug/nodes` | Every node class ComfyUI knows about |
| `POST` | `/debug/workflow` | Dry-run a graph, return the JSON without queueing |

Interactive docs at `/docs`.

## Layout

```
comfyui-auto/
├── server.py            # FastAPI web GUI — the main entry point
├── run.py               # CLI alternative
├── client.py            # ComfyUI API client: queue, poll /history, download /view
├── workflows/
│   ├── defaults.py      # shared negatives + is_flux() / is_sdxl() detection
│   ├── text2img.py      # text → image
│   ├── img2img.py       # edit an image
│   ├── flux.py          # FLUX.1 graphs
│   ├── kontext.py       # Flux Kontext instruction editing
│   ├── photomaker.py    # person from reference photos
│   └── video.py         # AnimateDiff text → video
├── static/index.html    # the entire frontend — inline CSS/JS, no build step
├── outputs/             # generated files (gitignored, volume-mounted)
├── Containerfile
└── run-podman.sh
```

## Design notes

- **Polling, not websockets.** The browser polls `/job/{id}` every 2s; the server polls ComfyUI's
  `/history/{prompt_id}` every 1.5s with a 600s timeout. Simple and reliable.
- **One thread per generation**, `daemon=True`. No queue, no worker pool.
- **Jobs are in-memory only** — no persistence, no eviction. Restarting the server loses them.
- **Uploads are ephemeral**, unlinked in the job's `finally` block.
- **Per-model defaults are an affordance, not a constraint.** Changing checkpoint overwrites the
  steps/CFG/resolution boxes; for FLUX it also relabels CFG → Guidance and hides the negative
  prompt.

## Known limitations

- **Video doesn't work out of the box.** The `video` task needs AnimateDiff-Evolved and
  VideoHelperSuite installed in ComfyUI, plus a motion module — and there's no GUI mode for it,
  only `run.py video`.
- **Flux Kontext and a local LLM won't co-exist on 12 GB of VRAM.** Kontext needs ~7 GB and
  ComfyUI keeps it resident after the job. Free it with:
  ```bash
  curl -X POST http://localhost:8188/free -H 'Content-Type: application/json' \
       -d '{"unload_models":true,"free_memory":true}'
  ```
- **Adding a checkpoint whose filename lacks `xl`** means adding it to both the backend keyword
  set (`workflows/defaults.py`) and the frontend `CKPT_CONFIGS` map.
- **Pony Diffusion V6 XL ignores plain style words** — it wants `score_9, score_8_up`-style tags
  typed into the manual prompt instead.
