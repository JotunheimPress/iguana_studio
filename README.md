# Iguana Studio

A prompt-first browser GUI for [ComfyUI](https://github.com/comfyanonymous/ComfyUI). You type a
prompt, pick a mode and press Generate. Iguana Studio builds the ComfyUI workflow graph, submits
it over ComfyUI's API, shows its progress and drops the result in a gallery. No node editor, no
wiring.

It's a frontend for **[AI Ecosystem](https://github.com/JotunheimPress/ai_ecosystem)**, which
runs ComfyUI (with the custom nodes and patches the modes below need) as a shared backend. The
page is written in Python and runs in the browser
([pytincture](https://pypi.org/project/pytincture/) and
[wapyt](https://github.com/WAwesome-AI/wa_pytincture_widgetset)).

**Documentation:** the [wiki](https://github.com/JotunheimPress/iguana_studio/wiki) has a user
guide (the modes, prompts, models, the gallery, troubleshooting) and a developer guide. Its source
is [`docs/wiki/`](docs/wiki/README.md).

## Modes

| Mode | What it does |
|---|---|
| **Generate** | Text to image. SD 1.5, SDXL, FLUX.1, FLUX.2 and Z-Image, picked from the model, with per-model defaults for size, steps and CFG/guidance, and a LoRA stack. |
| **Person** | Images of a specific person from one or more reference photos, with PuLID on FLUX.1-dev. |
| **Refine** | Image to image: re-noise an existing image with a denoise slider. |
| **Edit** | Instruction-based editing with Flux Kontext ("change the background to a snowy mountain"). What you don't mention is kept. |
| **Animate** | Image to video with WAN 2.2 TI2V 5B: describe the motion. |

Any result can be sent straight into Refine, Edit or Animate.

The sidebar is prompt-first: you write the subject, and the dropdowns (art style, setting,
lighting, camera, clothing, pose, focus, expression, eye colour) only *add* to it. All are off by
default, so a fresh session generates exactly what you typed, and the composed prompt is shown
live. Prompts can be saved and reused; your settings are remembered in the browser.

## Requirements

- **AI Ecosystem** (recommended), or any ComfyUI reachable from the container as
  `comfyui:8188` on the `ai-net` Podman network.
- **Podman** (rootless). A GPU is ComfyUI's business, not this app's.
- **Models in ComfyUI**, per mode. AI Ecosystem's `comfyui/INSTALL.md` lists the files and where
  they go:
  - Generate and Refine: any SD 1.5, SDXL, FLUX or Z-Image checkpoint.
  - Person: [ComfyUI_PuLID_Flux_ll](https://github.com/lldacing/ComfyUI_PuLID_Flux_ll) (AI
    Ecosystem installs it, with its patch for current ComfyUI), FLUX.1-dev (`flux1-dev-Q8_0.gguf`),
    the PuLID-FLUX weights, EVA-CLIP, facexlib and InsightFace `antelopev2`.
  - Edit: [ComfyUI-GGUF](https://github.com/city96/ComfyUI-GGUF) and a Flux Kontext GGUF, with its
    text encoders and VAE (about 12.5 GB).
  - Animate: WAN 2.2 TI2V 5B. ComfyUI supports it natively, so no custom node is needed.

## Running it

### With AI Ecosystem

Install it from the AI Ecosystem dashboard's Frontends screen, or with
`stack frontend add iguana_studio` (or clone this repo next to `ai-stack/`), then:

```bash
stack up                 # the backends, ComfyUI included
stack iguana_studio      # builds the image on the first start; http://localhost:7862
stack down iguana_studio
```

### On its own

```bash
cd comfyui-auto
./run-podman.sh                   # build if needed, then start on :7862
./run-podman.sh --rebuild         # rebuild the image first
./run-podman.sh --port 8862       # another host port
./run-podman.sh --build-only      # build, don't start
podman logs -f iguana
```

The container joins the `ai-net` network and reaches ComfyUI at `comfyui:8188`. Generated files
go to `comfyui-auto/outputs/` and saved prompts to `comfyui-auto/data/`; both are kept out of git.

### On your network

**Iguana Studio has no login.** The container is published on all interfaces, so any device on
your network can open `http://<this-machine>.local:7862` and generate, view and delete images.
It only answers to this machine's own names and addresses, which stops other web pages from
reaching it through your browser. `run-podman.sh` works those out at start, and
`IGUANA_ALLOWED_HOSTS=a,b` adds more. If your network isn't trusted, block port 7862 there.

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `COMFY_HOST` | `comfyui` | ComfyUI's host name |
| `COMFY_PORT` | `8188` | ComfyUI's port |
| `PORT` | `7862` | The port the GUI listens on |
| `IGUANA_ALLOWED_HOSTS` | set by `run-podman.sh` | Extra host names the GUI answers to |

## CLI

`run.py` is a thinner alternative for scripts: `text2img`, `img2img` and `video`, without Person
mode or the GUI's per-model tuning.

```bash
python run.py text2img "a cat on a windowsill, 35mm film photography"
python run.py img2img photo.png "make it snow" --denoise 0.55
```

Lightning checkpoints need their settings passed explicitly: `--steps 6 --cfg 2`.

## Development

The wiki's developer guide is the overview. `comfyui-auto/CLAUDE.md` has the full notes: the layout, how each mode's graph is built,
running from a virtualenv without rebuilding the image, and the tests (a golden test of the
prompt composer, per-workflow tests and a Playwright smoke test of every mode).

## Known limitations

- **VRAM is shared.** Flux Kontext, PuLID and WAN each want most of a 12 GB card. Stop the text
  model first (`stack down koboldcpp`) if a job runs out of memory.
- **Jobs live in memory.** Restarting the container loses running and finished jobs (not their
  files).
- **Pony Diffusion V6 XL ignores plain style words.** Type `score_9, score_8_up`-style tags into
  the prompt instead.

## License

[MIT](LICENSE).
