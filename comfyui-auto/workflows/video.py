"""Short video from a still image (or from text alone) — WAN 2.2 TI2V 5B.

Replaces the AnimateDiff module that used to live here. That one targeted `ADE_*` and
`VHS_*` nodes from two custom node packs, neither of which is installed, and it had never
run. It is not needed: ComfyUI v0.31.1 ships **native** WAN support, so this whole feature
costs zero custom nodes, zero `stack` CUSTOM_NODES rows and zero image rebuilds — only the
weights listed in `ai-stack/comfyui/INSTALL.md` §8.

**One graph, two entry points.** `Wan22ImageToVideoLatent` takes `start_image` as an
*optional* input, so image→video and text→video differ by exactly one key. Building them
as one spine (`_build`) means the sampler settings can never drift apart between the mode
you use from the GUI and the one you use from the CLI.

Sizing rules that are enforced here rather than trusted to the caller:
  * `length` must be **4n+1** — the 5B VAE compresses 4x temporally, and an off-grid
    length is rejected deep inside the sampler with a shape error that reads like a bug.
  * 1280x704 is the native training resolution. Going far under it degrades WAN the way
    512 degrades SDXL, which is the reasoning already written down in `defaults.py`.
"""

import random
from pathlib import Path

from client import upload_image
from workflows.defaults import NEGATIVE_VIDEO as DEFAULT_NEGATIVE

# All three are supplied by the operator — see ai-stack/comfyui/INSTALL.md §8.
DEFAULT_MODEL   = "wan2.2_ti2v_5B_fp16.safetensors"      # models/diffusion_models/
DEFAULT_CLIP    = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"  # models/text_encoders/
DEFAULT_VAE     = "wan2.2_vae.safetensors"               # models/vae/

# Native resolution and the frame grid the 5B VAE works on.
NATIVE_W, NATIVE_H = 1280, 704
FRAME_STEP  = 4        # length must be 4n+1
MIN_LENGTH  = 5
MAX_LENGTH  = 121      # ~5 s at 24 fps; the documented ceiling for this model
# 49 frames (~2 s) is not enough room for the model to finish an ordinary action: measured
# on a fixed seed, "touch her shoulder" started the reach and ran out of clip at 49, and
# completed at 81. Defaulting short made the model look like it was ignoring the prompt.
DEFAULT_LENGTH = 81    # ~3.4 s at 24 fps


def clamp_length(length: int) -> int:
    """Round `length` onto the 4n+1 grid, within [5, 121].

    Rounds *down* to the nearest valid value so a request can never silently cost more
    time than it asked for — a video length is a time budget as much as a size.
    """
    length = max(MIN_LENGTH, min(int(length), MAX_LENGTH))
    return ((length - 1) // FRAME_STEP) * FRAME_STEP + 1


def _build(
    prompt: str,
    negative_prompt: str,
    server_image: str | None,
    width: int,
    height: int,
    length: int,
    steps: int,
    cfg: float,
    seed: int,
    fps: int,
    shift: float,
    sampler: str,
    scheduler: str,
    filename_prefix: str,
) -> dict:
    """The shared spine. `server_image` is a filename already uploaded to ComfyUI's input
    folder, or None for text→video."""
    if seed == -1:
        seed = random.randint(0, 2**32 - 1)

    length = clamp_length(length)

    latent_inputs = {
        "vae": ["3", 0],
        "width": width,
        "height": height,
        "length": length,
        "batch_size": 1,
    }

    graph = {
        "1": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": DEFAULT_MODEL, "weight_dtype": "default"},
        },
        "2": {
            "class_type": "CLIPLoader",
            "inputs": {"clip_name": DEFAULT_CLIP, "type": "wan"},
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": DEFAULT_VAE},
        },
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["2", 0]},
        },
        "5": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["2", 0]},
        },
        # 6 is LoadImage, added below only for image→video.
        "7": {
            "class_type": "Wan22ImageToVideoLatent",
            "inputs": latent_inputs,
        },
        "8": {
            "class_type": "ModelSamplingSD3",
            "inputs": {"model": ["1", 0], "shift": shift},
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler,
                "scheduler": scheduler,
                "denoise": 1.0,
                "model": ["8", 0],
                "positive": ["4", 0],
                "negative": ["5", 0],
                "latent_image": ["7", 0],
            },
        },
        "10": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["9", 0], "vae": ["3", 0]},
        },
        "11": {
            "class_type": "CreateVideo",
            "inputs": {"images": ["10", 0], "fps": float(fps)},
        },
        # format/codec verified against this ComfyUI build: both are accepted in API
        # format as bare strings, and "auto" muxes h264 via the container's PyAV 17.
        "12": {
            "class_type": "SaveVideo",
            "inputs": {
                "video": ["11", 0],
                "filename_prefix": filename_prefix,
                "format": "mp4",
                "codec": "auto",
            },
        },
    }

    if server_image is not None:
        graph["6"] = {
            "class_type": "LoadImage",
            "inputs": {"image": server_image, "upload": "image"},
        }
        # Set on the graph directly rather than through the `latent_inputs` alias — the
        # aliasing works, but a link this load-bearing should be visible where it lands.
        # Omitted entirely (not passed as None) for text→video: the input is optional and
        # ComfyUI rejects a null where it expects an IMAGE link.
        graph["7"]["inputs"]["start_image"] = ["6", 0]

    return graph


def build_i2v(
    image_path: str | Path,
    prompt: str,
    negative_prompt: str = DEFAULT_NEGATIVE,
    width: int = NATIVE_W,
    height: int = NATIVE_H,
    length: int = DEFAULT_LENGTH,
    steps: int = 30,
    cfg: float = 5.0,
    seed: int = -1,
    fps: int = 24,
    shift: float = 8.0,
    sampler: str = "uni_pc",
    scheduler: str = "simple",
    filename_prefix: str = "video/iguana_i2v",
) -> dict:
    """Animate a still image. The prompt describes the *motion*, not the subject —
    the subject is already fixed by the image."""
    return _build(
        prompt=prompt, negative_prompt=negative_prompt,
        server_image=upload_image(image_path),
        width=width, height=height, length=length, steps=steps, cfg=cfg,
        seed=seed, fps=fps, shift=shift, sampler=sampler, scheduler=scheduler,
        filename_prefix=filename_prefix,
    )


def build_t2v(
    prompt: str,
    negative_prompt: str = DEFAULT_NEGATIVE,
    width: int = NATIVE_W,
    height: int = NATIVE_H,
    length: int = DEFAULT_LENGTH,
    steps: int = 30,
    cfg: float = 5.0,
    seed: int = -1,
    fps: int = 24,
    shift: float = 8.0,
    sampler: str = "uni_pc",
    scheduler: str = "simple",
    filename_prefix: str = "video/iguana_t2v",
) -> dict:
    """Video from a text prompt alone — same weights, same spine, no start image."""
    return _build(
        prompt=prompt, negative_prompt=negative_prompt, server_image=None,
        width=width, height=height, length=length, steps=steps, cfg=cfg,
        seed=seed, fps=fps, shift=shift, sampler=sampler, scheduler=scheduler,
        filename_prefix=filename_prefix,
    )
