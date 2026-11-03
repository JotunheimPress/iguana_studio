"""Text-to-image workflow — supports SD 1.5, SDXL, FLUX and Z-Image."""

import random
from workflows import lora as lora_chain
from workflows.defaults import NEGATIVE as DEFAULT_NEGATIVE, is_flux, is_sdxl, is_zimage

DEFAULT_CHECKPOINT = "sd_xl_base_1.0.safetensors"


def build(
    prompt: str,
    negative_prompt: str = DEFAULT_NEGATIVE,
    checkpoint: str = DEFAULT_CHECKPOINT,
    width: int = 1024,
    height: int = 1024,
    steps: int = 25,
    cfg: float = 7.0,
    seed: int = -1,
    sampler: str = "euler",
    scheduler: str = "normal",
    filename_prefix: str = "text2img",
    loras=None,
) -> dict:
    if is_zimage(checkpoint):
        # Steps/CFG come from the form as for any model (services/models.py stamps the
        # recommended ones on a model change); its own sampler and scheduler are fixed.
        from workflows.zimage import build as zimage_build
        return zimage_build(
            width=width, height=height,
            prompt=prompt, negative_prompt=negative_prompt, checkpoint=checkpoint,
            steps=steps, cfg=cfg, seed=seed,
            filename_prefix=filename_prefix, loras=loras,
        )

    if is_flux(checkpoint):
        from workflows.flux import build as flux_build
        return flux_build(
            prompt=prompt,
            checkpoint=checkpoint,
            width=width, height=height,
            steps=steps, cfg=cfg, seed=seed,
            sampler=sampler,
            scheduler="simple",
            filename_prefix=filename_prefix,
            loras=loras,
        )

    if seed == -1:
        seed = random.randint(0, 2**32 - 1)

    sdxl = is_sdxl(checkpoint)

    # SDXL needs CLIPTextEncodeSDXL for proper prompt following
    if sdxl:
        pos_node = {
            "class_type": "CLIPTextEncodeSDXL",
            "inputs": {
                "width": width, "height": height,
                "crop_w": 0, "crop_h": 0,
                "target_width": width, "target_height": height,
                "text_g": prompt, "text_l": prompt,
                "clip": ["1", 1],
            },
        }
        neg_node = {
            "class_type": "CLIPTextEncodeSDXL",
            "inputs": {
                "width": width, "height": height,
                "crop_w": 0, "crop_h": 0,
                "target_width": width, "target_height": height,
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

    workflow = {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        "2": pos_node,
        "3": neg_node,
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed, "steps": steps, "cfg": cfg,
                "sampler_name": sampler, "scheduler": scheduler,
                "denoise": 1.0,
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
            },
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": filename_prefix, "images": ["6", 0]},
        },
    }
    return lora_chain.apply(workflow, loras)
