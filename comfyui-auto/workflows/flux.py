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
"""

import random

from workflows import lora as lora_chain

DEFAULT_CHECKPOINT = "flux1-dev.safetensors"


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

    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        # FLUX positive conditioning — guidance baked in here
        "2": {
            "class_type": "CLIPTextEncodeFlux",
            "inputs": {
                "clip":     ["1", 1],
                "clip_l":   prompt,
                "t5xxl":    prompt,
                "guidance": guidance,
            },
        },
        # Empty negative — required by KSampler, but FLUX doesn't use it
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "", "clip": ["1", 1]},
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
            "inputs": {"samples": ["6", 0], "vae": ["1", 2]},
        },
        "8": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": filename_prefix, "images": ["7", 0]},
        },
    }
    return lora_chain.apply(workflow, loras)


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

    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        "2": {
            "class_type": "CLIPTextEncodeFlux",
            "inputs": {
                "clip":     ["1", 1],
                "clip_l":   prompt,
                "t5xxl":    prompt,
                "guidance": guidance,
            },
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "", "clip": ["1", 1]},
        },
        "4": {
            "class_type": "LoadImage",
            "inputs": {"image": server_image, "upload": "image"},
        },
        "5": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["4", 0], "vae": ["1", 2]},
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
            "inputs": {"samples": ["7", 0], "vae": ["1", 2]},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": filename_prefix, "images": ["8", 0]},
        },
    }
    return lora_chain.apply(workflow, loras)
