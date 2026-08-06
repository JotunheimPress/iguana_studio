"""Image-to-image (edit existing image) workflow — supports SD 1.5, SDXL, and FLUX."""

import random
from pathlib import Path

from client import upload_image
from workflows.defaults import NEGATIVE as DEFAULT_NEGATIVE, is_flux, is_sdxl

DEFAULT_CHECKPOINT = "sd_xl_base_1.0.safetensors"


def build(
    image_path: str | Path,
    prompt: str,
    negative_prompt: str = DEFAULT_NEGATIVE,
    checkpoint: str = DEFAULT_CHECKPOINT,
    denoise: float = 0.75,
    steps: int = 25,
    cfg: float = 7.0,
    seed: int = -1,
    sampler: str = "euler",
    scheduler: str = "normal",
    filename_prefix: str = "img2img",
) -> dict:
    """
    Build an img2img workflow. Auto-detects SD 1.5, SDXL, and FLUX.

    denoise: 0.0 = keep original, 1.0 = full redraw. 0.6–0.8 recommended for edits.
    """
    if is_flux(checkpoint):
        from workflows.flux import build_img2img as flux_img2img
        return flux_img2img(
            image_path=image_path,
            prompt=prompt,
            checkpoint=checkpoint,
            denoise=denoise,
            steps=steps, cfg=cfg, seed=seed,
            sampler=sampler,
            scheduler="simple",
            filename_prefix=filename_prefix,
        )

    if seed == -1:
        seed = random.randint(0, 2**32 - 1)

    server_image = upload_image(image_path)
    sdxl = is_sdxl(checkpoint)

    # For SDXL, use safe defaults — ComfyUI's LoadImage will handle resize
    w, h = (1024, 1024) if sdxl else (512, 512)

    if sdxl:
        pos_node = {
            "class_type": "CLIPTextEncodeSDXL",
            "inputs": {
                "width": w, "height": h,
                "crop_w": 0, "crop_h": 0,
                "target_width": w, "target_height": h,
                "text_g": prompt, "text_l": prompt,
                "clip": ["1", 1],
            },
        }
        neg_node = {
            "class_type": "CLIPTextEncodeSDXL",
            "inputs": {
                "width": w, "height": h,
                "crop_w": 0, "crop_h": 0,
                "target_width": w, "target_height": h,
                "text_g": negative_prompt, "text_l": negative_prompt,
                "clip": ["1", 1],
            },
        }
    else:
        pos_node = {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["1", 1]},
        }
        neg_node = {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["1", 1]},
        }

    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        "2": pos_node,
        "3": neg_node,
        "4": {
            "class_type": "LoadImage",
            "inputs": {"image": server_image, "upload": "image"},
        },
        "5": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["4", 0], "vae": ["1", 2]},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed, "steps": steps, "cfg": cfg,
                "sampler_name": sampler, "scheduler": scheduler,
                "denoise": denoise,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["5", 0],
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
