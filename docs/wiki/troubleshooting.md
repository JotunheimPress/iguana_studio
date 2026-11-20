# Troubleshooting

[Wiki home](README.md) · User guide

First steps for anything odd: the app's log (`podman logs -f iguana`, or `stack logs
iguana_studio`) and ComfyUI's log (`stack logs comfyui` with AI Ecosystem). An error in a job
card usually quotes ComfyUI's own message.

## A job runs out of memory, or crawls

Edit (Flux Kontext), Person (PuLID with FLUX.1-dev) and Animate (WAN) each want most of a 12 GB
card. If the text model is loaded too, they don't fit.

- With AI Ecosystem: stop the text model first (`stack down koboldcpp`), or free ComfyUI's memory
  from the dashboard's VRAM screen.
- After a big job, **ComfyUI keeps the model loaded**. If something else then can't start for
  lack of memory, ask ComfyUI to let go (no restart needed):

  ```bash
  curl -X POST http://localhost:8188/free -H 'Content-Type: application/json' \
       -d '{"unload_models":true,"free_memory":true}'
  ```

  Iguana Studio doesn't do this by itself: unloading another service's models without being
  asked would be a surprise.
- Smaller models help: FLUX.1 as a Q4 GGUF instead of Q8, 960×544 instead of 1280×704 for video.

## Jobs disappeared after a restart

Jobs are kept in memory only. Restarting the container loses running and finished jobs; the
files already written to `outputs/` stay.

## The model ignores my style words

- **Pony Diffusion V6 XL** mostly ignores plain style words. It was trained on tags like
  `score_9, score_8_up, source_anime`: type those into the prompt instead.
- **Edit redraws the whole picture**: write an instruction ("make the sky stormy"), not a
  description (see [Edit](modes.md#edit)).
- **Animate barely moves**: make it longer (81 frames or more) and check the source shows what
  should move (see [Animate](modes.md#animate)).

## Person mode made a stranger

PuLID found no face in any reference photo, so it ran without one. Use clear, front-facing
photos where the face isn't tiny, and FLUX.1-dev rather than schnell.

## Person mode fails on every image

With AI Ecosystem, `stack doctor` checks the PuLID node's patch. An error mentioning
`timestep_zero_index` means the node is unpatched; `stack install comfyui` applies the patch.

## The page says ComfyUI is unreachable

ComfyUI isn't running, or the container can't reach it. Start the backends (`stack up`) and
check that both containers are on `ai-net` (`podman network inspect ai-net`). For a ComfyUI
elsewhere, set `COMFY_HOST` and `COMFY_PORT`.

## Another device gets "400 Bad Request"

It reached the app by a name it doesn't answer to (see
[From other devices](getting-started.md#from-other-devices)). Add the name to
`IGUANA_ALLOWED_HOSTS` and restart, or restart after the machine got a new address.

## An upload is refused

Uploads are images only, up to 40 MB each.

## A model is missing from the picker

The picker lists what ComfyUI reports when the page loads. Check the file is in the right folder
([Models](models.md)), restart ComfyUI if it was added while it ran (`stack restart comfyui`), then
reload the page. A FLUX.2 or Z-Image file belongs in `models/diffusion_models/`, not
`checkpoints/`.
