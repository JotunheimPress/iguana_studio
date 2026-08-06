# ComfyUI Automation — Project Context

## What this is
A Python toolkit + web GUI for automating ComfyUI workflows on demand.
No clicking in the browser — jobs are submitted via API and results are saved automatically.

## User environment
- **ComfyUI**: Podman container on host network, data folder at `/home/user/ComfyUI/`
- **ComfyUI server**: runs on `http://localhost:8188` (host: `COMFY_HOST`, port: `COMFY_PORT` env vars)
- **Web GUI**: FastAPI server at `http://localhost:7861`
- **OS**: Linux (Fedora), Podman containers

## Installed models
- **Checkpoint (SD 1.5)**: `v1-5-pruned-emaonly-fp16.safetensors` — selectable in text2img/img2img, 512×512
- **Checkpoint (SDXL)**: `sd_xl_base_1.0.safetensors` — default for text2img/img2img/photomaker, 1024×1024
- **PhotoMaker V1**: `photomaker-v1.bin` — in `models/photomaker/`
- **PhotoMaker V2**: `photomaker-v2.bin` — in `models/photomaker/`, default, requires InsightFace
- **InsightFace**: `buffalo_1` (5 model files) — in `models/insightface/buffalo_1/`
- **AnimateDiff motion modules**: none yet — required for video workflow
- **Custom nodes**: `ComfyUI-PhotoMaker` (shiimizu) — installed and loading, provides `PhotoMakerLoaderPlus`, `PhotoMakerEncodePlus`, `PhotoMakerInsightFaceLoader`

## Python environments
- **ComfyUI Desktop venv**: `C:\Users\blade\Documents\ComfyUI\.venv` — this is the one ComfyUI actually uses for custom nodes
- **App internal venv**: `C:\Users\blade\AppData\Local\...\resources\ComfyUI\.venv` — do NOT install custom node deps here
- `insightface` 0.7.3 installed in the correct Desktop venv via prebuilt wheel

## Project structure
```
comfyui-auto/
├── server.py          # FastAPI web GUI (run this to use the browser UI)
├── run.py             # CLI alternative
├── client.py          # ComfyUI API client (queue, poll, download)
├── workflows/
│   ├── text2img.py    # Text → image (works now with SD 1.5)
│   ├── img2img.py     # Edit existing image via text (works now)
│   └── video.py       # Text → animated video (needs AnimateDiff setup)
├── static/
│   └── index.html     # Self-contained frontend (no build step)
├── outputs/           # All generated files saved here
├── temp/              # Temp storage for uploaded images (auto-cleaned)
└── requirements.txt
```

## How to run

**Containerized (default — via the ai-stack launcher).** Runs as a Podman container `iguana` on the
`ai-net` network, reaching ComfyUI at `host.containers.internal:8188`.
```bash
stack iguana                 # build (first run) + start on :7862  (or: ./run-podman.sh [--rebuild])
# → open http://localhost:7862 ; logs: podman logs -f iguana ; stop: stack down iguana
```
ComfyUI must be up (`stack up`). Env: `COMFY_HOST`/`COMFY_PORT` (default `host.containers.internal:8188`),
`PORT` (7862). Generated images persist in `outputs/` (a volume mount).

**Host dev (venv) — for the CLI or quick iteration.** `run.py` is a host CLI and still uses the venv.
```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt
PORT=7862 venv/bin/python server.py     # GUI    → http://localhost:7862
venv/bin/python run.py text2img "a cat" # CLI
```

## GUI tabs and their defaults
| Tab | Model | Resolution | Notes |
|-----|-------|-----------|-------|
| Text to Image | SDXL (selectable) | 1024×1024 | Switching to SD 1.5 auto-sets 512×512 |
| Edit Image | SDXL (selectable) | 1024×1024 | Same checkpoint dropdown as text2img |
| Animate to Video | SD 1.5 hardcoded | 512×512 | Needs AnimateDiff setup |
| Person (PhotoMaker) | SDXL hardcoded | 1024×1024 | V2 default, V1 selectable; trigger word `img` |

## Key design decisions
- **Polling not websockets** — `/job/{id}` endpoint polled every 2s; simpler and reliable
- **Threading** — each generation runs in a `daemon=True` thread; jobs stored in-memory dict
- **No build step** — frontend is a single self-contained HTML file with inline CSS/JS
- **Port config** — `COMFY_PORT` env var overrides the default 8188
- **Path traversal protection** — `/outputs/{filename}` uses `Path(filename).name` to strip any directory components
- **PhotoMaker V2 requires InsightFace** — `PhotoMakerInsightFaceLoader` node always included in workflow; provider set to "CUDA"

## Video setup (not yet done)
To enable the video workflow:
1. Install **ComfyUI-AnimateDiff-Evolved** via ComfyUI Manager
2. Install **ComfyUI-VideoHelperSuite** via ComfyUI Manager
3. Download `mm_sd_v15_v2.ckpt` → place in `Documents/ComfyUI/models/animatediff_models/`
4. Restart ComfyUI

## API endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serves the web GUI |
| GET | `/comfy-status` | Returns `{"running": bool}` |
| POST | `/generate` | Starts a job, returns `{"job_id": "..."}` |
| GET | `/job/{id}` | Returns `{status, files, message}` |
| GET | `/outputs/{filename}` | Serves a generated output file |

## Workflow node structure (ComfyUI API format)
Each workflow is a dict of `{"node_id": {"class_type": "...", "inputs": {...}}}`.
Node outputs are referenced as `["node_id", output_index]`.
- SD 1.5 checkpoint outputs: `[0]=model, [1]=clip, [2]=vae`
- KSampler output: `[0]=latent`
- VAEDecode output: `[0]=image`
