# Getting started

[Wiki home](README.md) · User guide

## What you need

- **ComfyUI**, reachable from Iguana Studio's container as `comfyui:8188` on the `ai-net`
  Podman network. [AI Ecosystem](https://github.com/JotunheimPress/ai_ecosystem) runs exactly
  that, with the custom nodes and patches the modes need, so it is the easy way.
- **Podman**, rootless. The GPU is ComfyUI's business, not Iguana Studio's: the app itself is a
  small Python container.
- **Models in ComfyUI** for the modes you want to use. Generate needs only a checkpoint; the
  other modes need more. [Models](models.md) lists them.

## Install and start

### With AI Ecosystem

Install it from the dashboard's Frontends screen (Iguana Studio is an official frontend), or
from a terminal:

```bash
stack frontend add iguana_studio   # clones its latest release next to ai-stack and builds it
stack up                           # the backends, ComfyUI included
stack iguana_studio                # starts it on http://localhost:7862
stack down iguana_studio           # stops it
stack frontend update iguana_studio  # its newest release, rebuilt
```

A plain `git clone` into the folder that holds `ai-stack/` works too; it then builds its image
on the first `stack iguana_studio`.

### On its own

```bash
cd comfyui-auto
./run-podman.sh                   # build if needed, then start on :7862
./run-podman.sh --rebuild         # rebuild the image first
./run-podman.sh --port 8862       # another host port
./run-podman.sh --build-only      # build, don't start
podman logs -f iguana             # its log
```

The container is called `iguana`, joins `ai-net` and reaches ComfyUI at `comfyui:8188`.

## The first start

Open `http://localhost:7862`. The top bar shows whether ComfyUI answers. Pick **Generate**,
choose a checkpoint, type a prompt and press **Generate**: progress shows as a bar with the
current step and an estimate of the time left, and the result appears under it and in the
gallery.

What it keeps, and where:

| What | Where |
|---|---|
| Generated images and videos | `comfyui-auto/outputs/` (thumbnails in `outputs/.thumbs/`) |
| Saved prompts | `comfyui-auto/data/saved-prompts.json` |
| Your current settings | the browser's local storage |
| Uploaded source images | `comfyui-auto/temp/`, deleted when the job ends |

`outputs/` and `data/` are kept out of git, so updating the app never touches them.

## From other devices

**Iguana Studio has no login.** The container listens on all interfaces, so any device on
your network can open `http://<the machine's name>.local:7862` and generate, view and delete
images.

It answers only to the machine's own names and addresses, which stops other web pages from
reaching it through your browser. `run-podman.sh` works those out at each start: the short host
name, `<name>.local`, `iguana` and the machine's IPv4 addresses. If you reach it some other way
(a DNS name of your own, a VPN name), add that with `IGUANA_ALLOWED_HOSTS=name1,name2` before
starting. A new LAN address needs a restart. If your network isn't trusted, block port 7862 on it.

## Settings

| Variable | Default | Purpose |
|---|---|---|
| `COMFY_HOST` | `comfyui` | ComfyUI's host name |
| `COMFY_PORT` | `8188` | ComfyUI's port |
| `PORT` | `7862` | The port the app listens on |
| `IGUANA_ALLOWED_HOSTS` | set by `run-podman.sh` | Extra host names it answers to |
| `IGUANA_STREAM_BUDGET` | `240` | Seconds a progress stream runs before handing over to a new one |

Next: [The five modes](modes.md).
