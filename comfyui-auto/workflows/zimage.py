"""Z-Image workflows (Tongyi-MAI): text → image and img2img, Turbo and base.

Built natively into ComfyUI, no custom node. Always a split load from three files:
  - diffusion model in models/diffusion_models (z_image_turbo_bf16 / z_image_bf16, or a
    finetune) → UNETLoader
  - text encoder qwen_3_4b in models/text_encoders → CLIPLoader, type "lumina2"
  - VAE ae.safetensors in models/vae → VAELoader (the same file FLUX uses)

Settings are ComfyUI's own templates (Comfy-Org/workflow_templates, image_z_image_turbo /
image_z_image): ModelSamplingAuraFlow shift 3, res_multistep + simple, EmptySD3LatentImage
(16-channel), 1024².
  - Turbo is distilled: 8 steps at CFG 1. At CFG 1 ComfyUI never evaluates the negative,
    which is what the template's ConditioningZeroOut amounts to, so the UI hides it.
  - Base: 25 steps at CFG 4, and the negative prompt does work.

Node "1" is the MODEL source and "1c" the CLIP source, as in flux.py's GGUF path, so the
LoRA chain (workflows/lora.py) splices in the same way.
"""

import random

from workflows import lora as lora_chain

DEFAULT_MODEL = "z_image_turbo_bf16.safetensors"
TEXT_ENCODER = "qwen_3_4b.safetensors"
VAE = "ae.safetensors"
SHIFT = 3.0
SAMPLER = "res_multistep"
SCHEDULER = "simple"


def is_turbo(model: str) -> bool:
    return "turbo" in model.lower()


def defaults_for(model: str) -> dict:
    return {"steps": 8, "cfg": 1.0} if is_turbo(model) else {"steps": 25, "cfg": 4.0}


def _loaders(model: str) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": model, "weight_dtype": "default"}},
        "1c": {"class_type": "CLIPLoader",
               "inputs": {"clip_name": TEXT_ENCODER, "type": "lumina2", "device": "default"}},
        "1v": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "1s": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": SHIFT}},
    }


def _settle(model: str, steps: int, cfg: float, seed: int) -> tuple[int, float, int]:
    defs = defaults_for(model)
    return (defs["steps"] if steps == -1 else steps,
            defs["cfg"] if cfg == -1 else float(cfg),
            random.randint(0, 2**32 - 1) if seed == -1 else seed)


def _graph(model, prompt, negative_prompt, latent_nodes, latent_ref, steps, cfg, seed,
           denoise, filename_prefix, loras) -> dict:
    workflow = {
        **_loaders(model),
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1c", 0]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative_prompt or "", "clip": ["1c", 0]}},
        **latent_nodes,
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed, "steps": steps, "cfg": cfg,
                "sampler_name": SAMPLER, "scheduler": SCHEDULER, "denoise": denoise,
                "model": ["1s", 0], "positive": ["2", 0], "negative": ["3", 0],
                "latent_image": latent_ref,
            },
        },
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1v", 0]}},
        "8": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": filename_prefix, "images": ["7", 0]}},
    }
    return lora_chain.apply(workflow, loras, ckpt_node="1", clip_ref=["1c", 0])


def build(
    prompt: str,
    negative_prompt: str = "",
    checkpoint: str = DEFAULT_MODEL,
    width: int = 1024,
    height: int = 1024,
    steps: int = -1,                 # -1 = Turbo 8 / base 25
    cfg: float = -1,                 # -1 = Turbo 1 / base 4
    seed: int = -1,
    filename_prefix: str = "zimage",
    loras=None,
) -> dict:
    steps, cfg, seed = _settle(checkpoint, steps, cfg, seed)
    latent = {"4": {"class_type": "EmptySD3LatentImage",
                    "inputs": {"width": width, "height": height, "batch_size": 1}}}
    return _graph(checkpoint, prompt, negative_prompt, latent, ["4", 0], steps, cfg, seed,
                  1.0, filename_prefix, loras)


def build_img2img(
    image_path,
    prompt: str,
    negative_prompt: str = "",
    checkpoint: str = DEFAULT_MODEL,
    denoise: float = 0.7,
    steps: int = -1,
    cfg: float = -1,
    seed: int = -1,
    filename_prefix: str = "zimage_img2img",
    loras=None,
) -> dict:
    from client import upload_image

    steps, cfg, seed = _settle(checkpoint, steps, cfg, seed)
    server_image = upload_image(image_path)
    latent = {
        "4": {"class_type": "LoadImage", "inputs": {"image": server_image, "upload": "image"}},
        "5": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["1v", 0]}},
    }
    return _graph(checkpoint, prompt, negative_prompt, latent, ["5", 0], steps, cfg, seed,
                  denoise, filename_prefix, loras)
