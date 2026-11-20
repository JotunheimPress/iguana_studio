# Workflow graphs

[Wiki home](README.md) · Developer guide

Each mode builds a ComfyUI graph in Python under
[`comfyui-auto/workflows/`](../../comfyui-auto/workflows/) and sends it to ComfyUI's API. The
details of every graph, and why it is shaped that way, are in
[`comfyui-auto/CLAUDE.md`](../../comfyui-auto/CLAUDE.md).

## The format

A graph is a dict of `{"node_id": {"class_type": ..., "inputs": {...}}}`; an input that comes
from another node is `["node_id", output_index]`. For example `CheckpointLoaderSimple` outputs
`[0]` model, `[1]` CLIP, `[2]` VAE.

`POST /debug/workflow` builds a graph from the same fields the page sends and returns it without
queueing it, and `GET /debug/nodes` lists the node classes ComfyUI has. Both help when ComfyUI
rejects a graph.

## The builders

| File | Builds |
|---|---|
| `defaults.py` | Model-family detection from the file name (`base_of()`), and the shared negative prompts |
| `text2img.py`, `img2img.py` | Generate and Refine; they hand FLUX.1, FLUX.2 and Z-Image to the builders below |
| `flux.py` | FLUX.1: an all-in-one checkpoint, or a GGUF loaded in parts (`UnetLoaderGGUF` + `DualCLIPLoader` + `VAELoader`) |
| `flux2.py` | FLUX.2 Klein and Dev: `SamplerCustomAdvanced` with `Flux2Scheduler`, following ComfyUI's templates |
| `zimage.py` | Z-Image Turbo and base, following ComfyUI's templates |
| `pulid.py` | Person: the FLUX.1 graph plus one `LoadImage` → `ResizeAndPadImage` per photo, batched into `ApplyPulidFlux` |
| `kontext.py` | Edit: ComfyUI's Flux Kontext template with a GGUF loader |
| `video.py` | Animate: WAN 2.2 TI2V 5B, image to video (text to video from the CLI) |
| `lora.py` | Splices a LoRA chain into any finished checkpoint-based graph |

**Family detection has one home**, `defaults.py`: `is_flux2()`, `is_zimage()`, `is_flux()` and
`is_sdxl()` classify a file name and `base_of()` returns `FLUX.2`, `Z-Image`, `FLUX`, `SDXL` or
`SD 1.5`. The server sends that with each model, so the page never guesses for itself.
Recommended settings per model are in `services/models.py` (`config_for()`).

Things that are easy to get wrong:

- **Kontext:** `FluxKontextImageScale` is required (skipping it gives mushy, warped output), the
  sampler's CFG is pinned to 1.0 and the strength is `FluxGuidance`, which the page sends in the
  `cfg` field.
- **WAN:** the length must be 4n+1 (the VAE compresses time 4×); `clamp_length()` rounds down
  onto that grid. `SaveVideo` reports its file under `images`, not `videos`. Video jobs get a
  30-minute timeout.
- **PuLID:** reference node ids grow with the number of photos (`ref_N`, `pad_N`, `batch_N`), the
  only graph that isn't a fixed shape. `start_at < end_at` is checked before queueing.

## LoRAs

`lora.apply()` rewrites a finished graph instead of being threaded through every builder.
Each checkpoint-based builder publishes MODEL at `["1", 0]` and CLIP at `["1", 1]` (split loads
pass their CLIP node, `["1c", 0]`), so it chains `LoraLoader` nodes (`lora_0`, `lora_1`, …) off
those outputs and repoints every consumer at the end of the chain. Two rules hold:

- The rewrite happens before the chain is added, so the first loader still reads the checkpoint.
- The VAE output is never touched: LoRAs don't patch it, and Refine has two VAE consumers.

Kontext and WAN have no single MODEL+CLIP source, so `apply()` refuses them and the page hides
the LoRA section in Edit and Animate.

## Adding a model family

Z-Image is the worked example:

1. Teach `defaults.py` to recognise it, and add it to `BASES`.
2. Write its builder under `workflows/`, and have `text2img` and `img2img` hand it over.
3. Add a `config_for()` branch in `services/models.py`.
4. If it isn't a checkpoint, list its loader's files in `server.list_checkpoints()`.
5. Add it to `BASE_ORDER` in `appcode/ui/panels.py`, so the picker groups it in order.
6. Add a test like `tests/test_zimage.py`.
