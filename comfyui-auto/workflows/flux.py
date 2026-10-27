"""
FLUX.1 workflows — supports merged checkpoints (dev and schnell variants).

Differences from SD/SDXL:
  - Uses CLIPTextEncodeFlux (separate clip_l / t5xxl inputs)
  - Uses ModelSamplingFlux to patch the model for proper shift-based scheduling
  - Uses EmptySD3LatentImage (16-channel latent, same as SD3)
  - cfg is always 1.0; guidance is embedded in the conditioning instead
  - Negative prompt is unused (pass empty string)
  - Recommended sampler: euler + simple scheduler

FLUX.1-dev:   guidance=3.5, steps=20
FLUX.1-schnell: guidance=1.0, steps=4  (distilled, much faster)

Two ways to load the model, chosen by the filename:
  - an all-in-one checkpoint (models/checkpoints) → CheckpointLoaderSimple, which hands
    out MODEL, CLIP and VAE from one file;
  - a GGUF diffusion model (models/unet, e.g. city96's flux1-schnell-Q4_K_S.gguf) →
    UnetLoaderGGUF + DualCLIPLoader (clip_l + t5xxl) + VAELoader (ae). This is the one that
    fits a 12 GB card: an fp8 all-in-one is ~12 GB of diffusion weights on its own. Needs
    the ComfyUI-GGUF custom node and the same three support files Kontext uses.
Both keep node "1" as the MODEL source, so the rest of each graph is identical.
"""

import random

from workflows import lora as lora_chain

DEFAULT_CHECKPOINT = "flux1-dev.safetensors"

# Support files for the split (GGUF) path — the same ones Kontext loads.
CLIP_L = "clip_l.safetensors"
T5 = "t5xxl_fp8_e4m3fn_scaled.safetensors"
VAE = "ae.safetensors"


def is_gguf(checkpoint: str) -> bool:
    return checkpoint.lower().endswith(".gguf")


def _loaders(checkpoint: str) -> tuple[dict, list, list, list]:
    """Loader nodes plus the (model, clip, vae) edges the rest of the graph wires to."""
    if is_gguf(checkpoint):
        nodes = {
            "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": checkpoint}},
            "1c": {"class_type": "DualCLIPLoader",
                   "inputs": {"clip_name1": CLIP_L, "clip_name2": T5, "type": "flux"}},
            "1v": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        }
        return nodes, ["1", 0], ["1c", 0], ["1v", 0]
    nodes = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}}}
    return nodes, ["1", 0], ["1", 1], ["1", 2]


def _apply_loras(workflow: dict, checkpoint: str, loras) -> dict:
    if is_gguf(checkpoint):
        return lora_chain.apply(workflow, loras, ckpt_node="1", clip_ref=["1c", 0])
    return lora_chain.apply(workflow, loras)


def _is_schnell(checkpoint: str) -> bool:
    return "schnell" in checkpoint.lower()


def _defaults_for(checkpoint: str) -> dict:
    if _is_schnell(checkpoint):
        return {"steps": 4, "guidance": 1.0}
    return {"steps": 20, "guidance": 3.5}


def build(
    prompt: str,
    negative_prompt: str = "",      # kept for API compat; FLUX ignores it
    checkpoint: str = DEFAULT_CHECKPOINT,
    width: int = 1024,
    height: int = 1024,
    steps: int = -1,                 # -1 = auto from checkpoint type
    cfg: float = -1,                 # -1 = auto (maps to guidance)
    seed: int = -1,
    sampler: str = "euler",
    scheduler: str = "simple",
    filename_prefix: str = "flux",
    loras=None,
) -> dict:
    if seed == -1:
        seed = random.randint(0, 2**32 - 1)

    defs = _defaults_for(checkpoint)
    if steps == -1:
        steps = defs["steps"]
    guidance = defs["guidance"] if cfg == -1 else float(cfg)

    loaders, _model, clip, vae = _loaders(checkpoint)
    workflow = {
        **loaders,
        # FLUX positive conditioning — guidance baked in here
        "2": {
            "class_type": "CLIPTextEncodeFlux",
            "inputs": {
                "clip":     clip,
                "clip_l":   prompt,
                "t5xxl":    prompt,
                "guidance": guidance,
            },
        },
        # Empty negative — required by KSampler, but FLUX doesn't use it
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "", "clip": clip},
        },
        # 16-channel latent (SD3/FLUX format)
        "4": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        # Patch model for shift-based FLUX scheduling
        "5": {
            "class_type": "ModelSamplingFlux",
            "inputs": {
                "model":      ["1", 0],
                "max_shift":  1.15,
                "base_shift": 0.5,
                "width":      width,
                "height":     height,
            },
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "seed":          seed,
                "steps":         steps,
                "cfg":           1.0,       # always 1.0; guidance lives in conditioning
                "sampler_name":  sampler,
                "scheduler":     scheduler,
                "denoise":       1.0,
                "model":         ["5", 0],
                "positive":      ["2", 0],
                "negative":      ["3", 0],
                "latent_image":  ["4", 0],
            },
        },
        "7": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["6", 0], "vae": vae},
        },
        "8": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": filename_prefix, "images": ["7", 0]},
        },
    }
    return _apply_loras(workflow, checkpoint, loras)


def build_img2img(
    image_path,
    prompt: str,
    negative_prompt: str = "",
    checkpoint: str = DEFAULT_CHECKPOINT,
    denoise: float = 0.7,
    steps: int = -1,
    cfg: float = -1,
    seed: int = -1,
    sampler: str = "euler",
    scheduler: str = "simple",
    filename_prefix: str = "flux_img2img",
    loras=None,
) -> dict:
    from client import upload_image

    if seed == -1:
        seed = random.randint(0, 2**32 - 1)

    defs = _defaults_for(checkpoint)
    if steps == -1:
        steps = defs["steps"]
    guidance = defs["guidance"] if cfg == -1 else float(cfg)

    server_image = upload_image(image_path)

    loaders, _model, clip, vae = _loaders(checkpoint)
    workflow = {
        **loaders,
        "2": {
            "class_type": "CLIPTextEncodeFlux",
            "inputs": {
                "clip":     clip,
                "clip_l":   prompt,
                "t5xxl":    prompt,
                "guidance": guidance,
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "", "clip": clip},
        },
        "4": {
            "class_type": "LoadImage",
            "inputs": {"image": server_image, "upload": "image"},
        },
        "5": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["4", 0], "vae": vae},
        },
        "6": {
            "class_type": "ModelSamplingFlux",
            "inputs": {
                "model":      ["1", 0],
                "max_shift":  1.15,
                "base_shift": 0.5,
                "width":      1024,
                "height":     1024,
            },
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "seed":          seed,
                "steps":         steps,
                "cfg":           1.0,
                "sampler_name":  sampler,
                "scheduler":     scheduler,
                "denoise":       denoise,
                "model":         ["6", 0],
                "positive":      ["2", 0],
                "negative":      ["3", 0],
                "latent_image":  ["5", 0],
            },
        },
        "8": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["7", 0], "vae": vae},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]},
        },
    }
    return _apply_loras(workflow, checkpoint, loras)
