"""
Flux.1 Kontext [dev] — instruction-driven image editing.

Unlike img2img, this does not re-noise the source and hope. The image is encoded to
a latent and attached to the *conditioning* via ReferenceLatent, so the model sees
the original as context and applies the prompt as an instruction:

    "change her jacket to red"      "remove the person in the background"
    "make it winter"                "turn this into a pencil sketch"

Describe the *change*, not the whole scene — Kontext keeps everything you don't
mention. Phrasing it like a text2img prompt ("a woman in a red jacket, 8k, detailed")
tends to redraw the picture instead of editing it.

Requires the **ComfyUI-GGUF** custom node (city96) for UnetLoaderGGUF, plus four
model files (see the project CLAUDE.md for sources):
    models/unet/flux1-kontext-dev-Q4_K_M.gguf
    models/text_encoders/clip_l.safetensors
    models/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors
    models/vae/ae.safetensors
If generation fails with an unknown node type, the custom node is missing.

Graph mirrors ComfyUI's own `flux_kontext_dev_basic` template, with UNETLoader
swapped for UnetLoaderGGUF (the fp8 build needs ~20 GB VRAM; this card has 12).
"""

import random
from pathlib import Path

from client import upload_image

DEFAULT_UNET = "flux1-kontext-dev-Q4_K_M.gguf"
DEFAULT_CLIP_L = "clip_l.safetensors"
DEFAULT_T5 = "t5xxl_fp8_e4m3fn_scaled.safetensors"
DEFAULT_VAE = "ae.safetensors"

# Kontext is a guidance-distilled FLUX model: CFG is pinned to 1.0 and the real
# knob is FluxGuidance. 2.5 is the template default — lower drifts from the
# instruction, higher over-bakes and posterizes.
DEFAULT_GUIDANCE = 2.5
DEFAULT_STEPS = 20
CFG = 1.0


def build(
    image_path: str | Path,
    prompt: str,
    unet: str = DEFAULT_UNET,
    clip_l: str = DEFAULT_CLIP_L,
    t5: str = DEFAULT_T5,
    vae: str = DEFAULT_VAE,
    guidance: float = DEFAULT_GUIDANCE,
    steps: int = DEFAULT_STEPS,
    seed: int = -1,
    sampler: str = "euler",
    scheduler: str = "simple",
    filename_prefix: str = "kontext",
) -> dict:
    """
    Build a Flux Kontext edit workflow.

    Args:
        image_path: Local path to the source image; uploaded to ComfyUI first.
        prompt:     The edit instruction (see module docstring on phrasing).
        guidance:   FluxGuidance strength. 2.5 default; ~1.5 subtle, ~4 forceful.
        steps:      Sampling steps. 20 is the template default.
        seed:       -1 picks a random one.

    Note there is no negative prompt and no denoise: the negative is a zeroed-out
    copy of the positive conditioning (ConditioningZeroOut), which is what a
    distilled model expects, and sampling always runs at denoise 1.0 because the
    source enters through ReferenceLatent rather than through a partially-noised
    latent.
    """
    if seed == -1:
        seed = random.randint(0, 2**32 - 1)

    image_name = upload_image(image_path)

    return {
        "1": {
            "class_type": "UnetLoaderGGUF",
            "inputs": {"unet_name": unet},
        },
        "2": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": clip_l,
                "clip_name2": t5,
                "type": "flux",
                "device": "default",
            },
        },
        "3": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": vae},
        },
        "4": {
            "class_type": "LoadImage",
            "inputs": {"image": image_name},
        },
        # Snaps the source to a resolution Kontext was trained on. Skipping this is
        # the single most common cause of mushy or warped Kontext output.
        "5": {
            "class_type": "FluxKontextImageScale",
            "inputs": {"image": ["4", 0]},
        },
        "6": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["5", 0], "vae": ["3", 0]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["2", 0]},
        },
        # The edit itself: binds the source latent to the text conditioning.
        "8": {
            "class_type": "ReferenceLatent",
            "inputs": {"conditioning": ["7", 0], "latent": ["6", 0]},
        },
        "9": {
            "class_type": "FluxGuidance",
            "inputs": {"conditioning": ["8", 0], "guidance": guidance},
        },
        "10": {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["7", 0]},
        },
        "11": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "seed": seed,
                "steps": steps,
                "cfg": CFG,
                "sampler_name": sampler,
                "scheduler": scheduler,
                "positive": ["9", 0],
                "negative": ["10", 0],
                "latent_image": ["6", 0],
                "denoise": 1.0,
            },
        },
        "12": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["11", 0], "vae": ["3", 0]},
        },
        "13": {
            "class_type": "SaveImage",
            "inputs": {"images": ["12", 0], "filename_prefix": filename_prefix},
        },
    }
