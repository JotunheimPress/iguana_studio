# Architecture

[Wiki home](README.md) · Developer guide

The full notes, with the reasons and measurements behind each choice, are in
[`comfyui-auto/CLAUDE.md`](../../comfyui-auto/CLAUDE.md). This page is the map.

## The pieces

| Piece | Where | Reached at |
|---|---|---|
| Iguana Studio | Podman container `iguana` on network `ai-net` | `http://localhost:7862` |
| ComfyUI | its own container on `ai-net` (AI Ecosystem's) | `comfyui:8188`, by name on `ai-net` |
| `outputs/` | bind mount of `comfyui-auto/outputs/` | `/app/outputs` |
| `data/` | bind mount of `comfyui-auto/data/` | `/app/data` |

`comfyui:8188` resolves only on `ai-net`, so joining that network is required.
[`run-podman.sh`](../../comfyui-auto/run-podman.sh) builds the image (amd64, `python:3.13-slim`
plus the wapyt wheel) and starts it there. [`frontend.json`](../../frontend.json) at the repo
root is what makes AI Ecosystem list it as a frontend.

## The code

```
comfyui-auto/
├── service.py      # the server: the pytincture app, plus plain routes in front of it
├── server.py       # what the BFFs call: models, gallery, outputs, thumbnails, saved prompts
├── services/
│   ├── jobs.py     # the job table, one thread per job, parameters, progress and ETA
│   └── models.py   # recommended steps, CFG and size per model
├── appcode/        # the page (pytincture's modules_path)
│   ├── iguana.py   #   the shell: top bar, layout, mode tabs, generate, upload
│   ├── ui/         #   prompt, modifiers, sidebar, LoRAs, panels, jobs, gallery, viewer
│   ├── bff/        #   studio.py (models, jobs, the progress stream), prompts.py, gallery.py
│   └── static/iguana.css
├── client.py       # ComfyUI's API: queue, websocket progress, /history, downloads
├── workflows/      # one builder per mode and model family (see Workflow graphs)
├── run.py          # the CLI
└── tests/
```

## Python in the browser

The page is **Python running in the browser** (Pyodide), served by
[pytincture](https://pypi.org/project/pytincture/) with the
[wapyt](https://github.com/WAwesome-AI/wa_pytincture_widgetset) widget set. There is no
JavaScript build step: `appcode/` is a set of Python modules that pytincture ships to the
browser, plus one stylesheet.

- **Everything request/response is a BFF call** ("backend for frontend"): Python classes under
  `appcode/bff/` whose methods the page calls as if they were local. `Studio` (models, LoRAs,
  ComfyUI's status, `generate`, `from_output`, `job`, and `follow`, the progress stream),
  `Prompts` (`all`, `save`, `delete`) and `Gallery` (`items`, `delete`). `/iguana/bff-docs`
  lists them.
- **Binary stays plain HTTP**, as routes `service.py` registers in front of pytincture's own:

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Redirects to `/iguana/`, the page |
| GET | `/api/health` | `{"ok": true}`, for the container healthcheck and `stack status` |
| POST | `/upload` | Source images, one per request, images only, up to 40 MB → ids |
| GET | `/outputs/{file}` | One generated file |
| GET | `/thumbs/{file}` | A 280 px WebP gallery thumbnail, made once and cached in `outputs/.thumbs/` |
| GET | `/debug/nodes` | Every node class ComfyUI knows |
| POST | `/debug/workflow` | Build a graph and return it without queueing it |

- **BFF modules are re-executed on every call**, so they hold no state. The job table and
  caches live in `services/`.

## A job, end to end

1. The page sends `Studio.generate(task, fields, upload_ids)`. `jobs.params_for` checks and
   converts the fields; a bad value fails the request, not a queued job.
2. A thread builds the graph (`workflows/`), opens ComfyUI's websocket, then queues the graph
   with the same client id. Opening the socket first means no early progress message is missed.
3. ComfyUI's `progress` messages give the step; `jobs.view()` adds the phase (from the running
   node's class) and an ETA measured from the steps so far.
4. The page follows the job over `Studio.follow()`, a stream that sends changes and a heartbeat.
   It ends itself after `IGUANA_STREAM_BUDGET` seconds and the page reconnects, which is how a
   30-minute video gets past pytincture's 300 s stream limit. The job id is in `sessionStorage`,
   so a reload reconnects too.
5. When it finishes, `client.py` downloads the outputs into `outputs/`, thumbnails are made in
   the background, and uploaded sources are deleted.

If the websocket can't be had, or drops, the job falls back to polling ComfyUI's `/history`.
It is never queued twice. Jobs live in memory only, one thread each, with no queue.

## Security

- **No login.** The container listens on all interfaces; anyone on the LAN can use it.
- **Allowed hosts.** It answers only to loopback and the names in `IGUANA_ALLOWED_HOSTS` (set by
  `run-podman.sh` to the machine's names and addresses); anything else gets 400. That blocks DNS
  rebinding, where another web page points its own name at this machine to drive the app from
  your browser.
- **File names.** Outputs and deletes strip any directory part and accept only media suffixes.
  Uploads are named by the server (`up-<hex>.<ext>`); BFF calls accept only ids of that shape, and
  `from_output` only names of images already in `outputs/`.
- **No markup injection.** The gallery's menus are built from escaped `data-` attributes read by
  delegated listeners, never inline handlers.
