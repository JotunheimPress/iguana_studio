"""FLUX.2 workflows (Black Forest Labs): text → image and img2img, Dev and Klein.

Native in ComfyUI, no custom node; always a split load from models/diffusion_models. Graphs
follow ComfyUI's templates (Comfy-Org/workflow_templates: image_flux2_text_to_image,
image_flux2_klein_text_to_image, image_flux2_text_to_image_9b). Unlike FLUX.1 there is no
KSampler: RandomNoise + a guider + KSamplerSelect(euler) + Flux2Scheduler sigmas go into
SamplerCustomAdvanced, on an EmptyFlux2LatentImage, decoded with the FLUX.2 VAE.

Three variants, told apart by the file name:
  - Dev (32B, "dev"): Mistral 3 Small text encoder; BasicGuider on FluxGuidance (4.0);
    20 steps; no negative. The form's CFG box carries the guidance, as for FLUX.1.
  - Klein distilled (4B / 9B, e.g. flux-2-klein-4b): 4 steps, CFGGuider at 1 with a zeroed
    negative — at CFG 1 the negative is never evaluated, so the UI hides it.
  - Klein base ("base" in the name, e.g. flux-2-klein-base-4b): 20 steps, CFGGuider at 5,
    and the negative prompt works.
Klein 4B reads qwen_3_4b (the same file Z-Image uses), 9B qwen_3_8b.

Text encoder and VAE: each comes in several precisions (bf16 / fp8 / fp4), and the Dev and
9B templates use the newer full_encoder_small_decoder VAE where 4B uses flux2-vae. So the
builder takes the first installed file from a preference list (`pick`), asking ComfyUI what
is installed; with ComfyUI unreachable it falls back to the first name, and the job then
fails with ComfyUI's own "file not found" rather than a guess.

Img2img (Refine): the image is VAE-encoded and sampled over the tail of the schedule,
SplitSigmasDenoise's low half, from a schedule of steps/denoise so that the requested number
of steps actually runs. LoRAs splice in as for the GGUF FLUX.1 path: node "1" MODEL, "1c" CLIP.
"""

import math
import random
import re

from workflows import lora as lora_chain

DEFAULT_MODEL = "flux-2-klein-4b.safetensors"

_TE = {
    "dev": ("mistral_3_small_flux2_fp8.safetensors", "mistral_3_small_flux2_bf16.safetensors",
            "mistral_3_small_flux2_fp4_mixed.safetensors"),
    "9b": ("qwen_3_8b_fp8mixed.safetensors", "qwen_3_8b.safetensors",
           "qwen_3_8b_fp4mixed.safetensors"),
    "4b": ("qwen_3_4b.safetensors", "qwen_3_4b_fp4_flux2.safetensors"),
}
_VAE = ("flux2-vae.safetensors", "full_encoder_small_decoder.safetensors")


def variant(model: str) -> str:
    low = model.lower()
    if "dev" in low:
        return "dev"
    return "9b" if re.search(r"9b", low) else "4b"


def is_distilled(model: str) -> bool:
    """Klein without "base" is the 4-step distilled model. Dev is not a Klein."""
    return variant(model) != "dev" and "base" not in model.lower()


def uses_negative(model: str) -> bool:
    return variant(model) != "dev" and not is_distilled(model)


def defaults_for(model: str) -> dict:
    """{steps, cfg}. For Dev `cfg` is FluxGuidance, for Klein the CFGGuider scale."""
    if variant(model) == "dev":
        return {"steps": 20, "cfg": 4.0}
    return {"steps": 4, "cfg": 1.0} if is_distilled(model) else {"steps": 20, "cfg": 5.0}


def _installed(loader: str, field: str) -> list[str] | None:
    try:
        import requests
        from client import COMFY_URL

        r = requests.get(f"{COMFY_URL}/object_info/{loader}", timeout=5)
        r.raise_for_status()
        return r.json()[loader]["input"]["required"][field][0]
    except Exception:
        return None


def pick(prefs: tuple[str, ...], installed: list[str] | None) -> str:
    for name in prefs:
        if installed is None or name in installed:
            return name
    return prefs[0]


def _loaders(model: str, text_encoder: str | None, vae: str | None) -> dict:
    te = text_encoder or pick(_TE[variant(model)], _installed("CLIPLoader", "clip_name"))
    vae = vae or pick(_VAE, _installed("VAELoader", "vae_name"))
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": model, "weight_dtype": "default"}},
        "1c": {"class_type": "CLIPLoader",
               "inputs": {"clip_name": te, "type": "flux2", "device": "default"}},
        "1v": {"class_type": "VAELoader", "inputs": {"vae_name": vae}},
    }


def _guider(model: str, cfg: float, negative_prompt: str) -> dict:
    pos = {"class_type": "CLIPTextEncode", "inputs": {"text": None, "clip": ["1c", 0]}}
    if variant(model) == "dev":
        return {
            "2": pos,
            "2g": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["2", 0], "guidance": cfg}},
            "g": {"class_type": "BasicGuider", "inputs": {"model": ["1", 0], "conditioning": ["2g", 0]}},
        }
    if is_distilled(model):
        neg = {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["2", 0]}}
    else:
        neg = {"class_type": "CLIPTextEncode",
               "inputs": {"text": negative_prompt or "", "clip": ["1c", 0]}}
    return {
        "2": pos,
        "3": neg,
        "g": {"class_type": "CFGGuider",
              "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0], "cfg": cfg}},
    }


def _settle(model, steps, cfg, seed):
    d = defaults_for(model)
    return (d["steps"] if steps == -1 else steps, d["cfg"] if cfg == -1 else float(cfg),
            random.randint(0, 2**32 - 1) if seed == -1 else seed)


def _finish(workflow: dict, prompt: str, filename_prefix: str, loras) -> dict:
    workflow["2"]["inputs"]["text"] = prompt
    workflow.update({
        "n": {"class_type": "RandomNoise", "inputs": {"noise_seed": workflow.pop("_seed")}},
        "k": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "6": {"class_type": "SamplerCustomAdvanced",
              "inputs": {"noise": ["n", 0], "guider": ["g", 0], "sampler": ["k", 0],
                         "sigmas": workflow.pop("_sigmas"), "latent_image": workflow.pop("_latent")}},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1v", 0]}},
        "8": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": filename_prefix, "images": ["7", 0]}},
    })
    return lora_chain.apply(workflow, loras, ckpt_node="1", clip_ref=["1c", 0])


def build(
    prompt: str,
    negative_prompt: str = "",
    checkpoint: str = DEFAULT_MODEL,
    width: int = 1024,
    height: int = 1024,
    steps: int = -1,
    cfg: float = -1,
    seed: int = -1,
    filename_prefix: str = "flux2",
    loras=None,
    text_encoder: str | None = None,
    vae: str | None = None,
) -> dict:
    steps, cfg, seed = _settle(checkpoint, steps, cfg, seed)
    workflow = {
        **_loaders(checkpoint, text_encoder, vae),
        **_guider(checkpoint, cfg, negative_prompt),
        "4": {"class_type": "EmptyFlux2LatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "s": {"class_type": "Flux2Scheduler", "inputs": {"steps": steps, "width": width, "height": height}},
        "_seed": seed, "_sigmas": ["s", 0], "_latent": ["4", 0],
    }
    return _finish(workflow, prompt, filename_prefix, loras)


def build_img2img(
    image_path,
    prompt: str,
    negative_prompt: str = "",
    checkpoint: str = DEFAULT_MODEL,
    denoise: float = 0.7,
    steps: int = -1,
    cfg: float = -1,
    seed: int = -1,
    filename_prefix: str = "flux2_img2img",
    loras=None,
    text_encoder: str | None = None,
    vae: str | None = None,
    server_image: str | None = None,
) -> dict:
    steps, cfg, seed = _settle(checkpoint, steps, cfg, seed)
    if server_image is None:
        from client import upload_image
        server_image = upload_image(image_path)
    denoise = min(max(float(denoise), 0.01), 1.0)
    workflow = {
        **_loaders(checkpoint, text_encoder, vae),
        **_guider(checkpoint, cfg, negative_prompt),
        "4": {"class_type": "LoadImage", "inputs": {"image": server_image, "upload": "image"}},
        "5": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["1v", 0]}},
        "5s": {"class_type": "GetImageSize", "inputs": {"image": ["4", 0]}},
        # Flux2Scheduler shifts by resolution, so it gets the source's real size.
        "s": {"class_type": "Flux2Scheduler",
              "inputs": {"steps": math.ceil(steps / denoise), "width": ["5s", 0], "height": ["5s", 1]}},
        "sp": {"class_type": "SplitSigmasDenoise", "inputs": {"sigmas": ["s", 0], "denoise": denoise}},
        "_seed": seed, "_sigmas": ["sp", 1], "_latent": ["5", 0],
    }
    return _finish(workflow, prompt, filename_prefix, loras)
