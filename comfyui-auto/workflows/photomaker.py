"""
PhotoMaker workflow — generate images of a specific person from reference photos.

Uses the built-in ComfyUI PhotoMaker nodes (no custom node required).

Usage:
  - Upload 2–5 photos of the same person
  - Include the trigger word "photomaker" in your prompt to refer to them:
      "a photo of photomaker woman hiking in the mountains"
      "portrait of photomaker man wearing a suit, professional headshot"
"""

import random
from pathlib import Path
from client import upload_image

DEFAULT_CHECKPOINT   = "sd_xl_base_1.0.safetensors"
DEFAULT_PHOTOMAKER   = "photomaker-v1.bin"
DEFAULT_NEGATIVE     = (
    "ugly, blurry, low quality, deformed face, bad anatomy, "
    "watermark, signature, extra limbs"
)
TRIGGER_WORD = "img"


def build(
    image_paths: list[str | Path],
    prompt: str,
    negative_prompt: str = DEFAULT_NEGATIVE,
    checkpoint: str = DEFAULT_CHECKPOINT,
    photomaker_model: str = DEFAULT_PHOTOMAKER,
    width: int = 1024,
    height: int = 1024,
    steps: int = 25,
    cfg: float = 7.0,
    seed: int = -1,
    sampler: str = "euler",
    scheduler: str = "normal",
    filename_prefix: str = "photomaker",
) -> dict:
    """
    Build a PhotoMaker ComfyUI workflow using the built-in nodes.

    Args:
        image_paths:        List of local paths to reference images (2–5 recommended).
        prompt:             Must include the trigger word "photomaker" to refer to the person.
                            e.g. "professional portrait of photomaker man in a suit"
        negative_prompt:    What to avoid.
        checkpoint:         SD 1.5 checkpoint filename.
        photomaker_model:   PhotoMaker model filename in models/photomaker/.
        width / height:     Output resolution.
        steps / cfg / seed: Standard sampling parameters.
    """
    if not image_paths:
        raise ValueError("At least one reference image is required.")

    if TRIGGER_WORD not in prompt:
        raise ValueError(
            f'Prompt must contain the trigger word "{TRIGGER_WORD}". '
            f'Example: "portrait of {TRIGGER_WORD} woman at the beach"'
        )

    if seed == -1:
        seed = random.randint(0, 2**32 - 1)

    # Upload all reference images to ComfyUI
    server_filenames = [upload_image(p) for p in image_paths]
    N = len(server_filenames)

    workflow = {}

    # ── Fixed nodes ──────────────────────────────────────────────────────────
    workflow["1"] = {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": checkpoint},
    }
    workflow["2"] = {
        "class_type": "PhotoMakerLoaderPlus",
        "inputs": {"photomaker_model_name": photomaker_model},
    }
    workflow["3"] = {
        "class_type": "PhotoMakerInsightFaceLoader",
        "inputs": {"provider": "CUDA"},
    }

    # ── LoadImage nodes (one per reference image, starting at node 4) ─────────
    for i, filename in enumerate(server_filenames):
        workflow[str(4 + i)] = {
            "class_type": "LoadImage",
            "inputs": {"image": filename, "upload": "image"},
        }

    # ── Batch all reference images together ───────────────────────────────────
    if N == 1:
        final_image_ref = ["4", 0]
        next_id = 5
    else:
        batch_start = 4 + N
        workflow[str(batch_start)] = {
            "class_type": "ImageBatch",
            "inputs": {"image1": ["4", 0], "image2": ["5", 0]},
        }
        last_ref = [str(batch_start), 0]
        current = batch_start + 1

        for i in range(2, N):
            workflow[str(current)] = {
                "class_type": "ImageBatch",
                "inputs": {"image1": last_ref, "image2": [str(4 + i), 0]},
            }
            last_ref = [str(current), 0]
            current += 1

        final_image_ref = last_ref
        next_id = current

    # ── PhotoMaker encode (positive conditioning) ─────────────────────────────
    pm_id  = str(next_id)
    neg_id = str(next_id + 1)
    lat_id = str(next_id + 2)
    sam_id = str(next_id + 3)
    dec_id = str(next_id + 4)
    sav_id = str(next_id + 5)

    workflow[pm_id] = {
        "class_type": "PhotoMakerEncodePlus",
        "inputs": {
            "photomaker":      ["2", 0],
            "image":           final_image_ref,
            "clip":            ["1", 1],
            "trigger_word":    TRIGGER_WORD,
            "text":            prompt,
            "insightface_opt": ["3", 0],
        },
    }
    workflow[neg_id] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": negative_prompt, "clip": ["1", 1]},
    }
    workflow[lat_id] = {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": width, "height": height, "batch_size": 1},
    }
    workflow[sam_id] = {
        "class_type": "KSampler",
        "inputs": {
            "seed":         seed,
            "steps":        steps,
            "cfg":          cfg,
            "sampler_name": sampler,
            "scheduler":    scheduler,
            "denoise":      1.0,
            "model":        ["1", 0],
            "positive":     [pm_id, 0],
            "negative":     [neg_id, 0],
            "latent_image": [lat_id, 0],
        },
    }
    workflow[dec_id] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": [sam_id, 0], "vae": ["1", 2]},
    }
    workflow[sav_id] = {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": filename_prefix, "images": [dec_id, 0]},
    }

    return workflow
