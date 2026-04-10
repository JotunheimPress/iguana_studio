"""
Text/image-to-video workflow using AnimateDiff Evolved.

SETUP REQUIRED before this workflow will work:
  1. Install custom node:
       ComfyUI Manager → search "AnimateDiff Evolved" → Install
       (or clone https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved
        into ComfyUI/custom_nodes/)

  2. Install video helper node (for saving .gif/.mp4):
       ComfyUI Manager → search "ComfyUI-VideoHelperSuite" → Install

  3. Download a motion module into models/animatediff_models/:
       Recommended: mm_sd_v15_v2.ckpt
       Source: https://huggingface.co/guoyww/animatediff/tree/main

  4. Restart ComfyUI.

Once set up, this workflow animates a scene described by your text prompt
using your SD 1.5 checkpoint as the base model.
"""

import random
from pathlib import Path


DEFAULT_CHECKPOINT = "v1-5-pruned-emaonly-fp16.safetensors"
DEFAULT_MOTION_MODULE = "mm_sd_v15_v2.ckpt"
DEFAULT_NEGATIVE = (
    "ugly, blurry, low quality, watermark, deformed, flickering, static, still"
)

REQUIRED_NODES = [
    "ADE_AnimateDiffLoaderWithContext",
    "ADE_UseEvolvedSampling",
    "VHS_VideoCombine",
]


def check_setup(comfy_base: str | Path = None) -> list[str]:
    """
    Check if AnimateDiff dependencies exist. Returns a list of missing items.
    Pass comfy_base as the path to your ComfyUI folder (e.g. C:/Users/blade/Documents/ComfyUI).
    """
    issues = []
    if comfy_base is None:
        return issues  # skip filesystem checks if no path given

    base = Path(comfy_base)
    motion_path = base / "models" / "animatediff_models" / DEFAULT_MOTION_MODULE
    if not motion_path.exists():
        issues.append(
            f"Missing motion module: {motion_path}\n"
            "  → Download mm_sd_v15_v2.ckpt from "
            "https://huggingface.co/guoyww/animatediff"
        )

    ade_node = base / "custom_nodes" / "ComfyUI-AnimateDiff-Evolved"
    if not ade_node.exists():
        issues.append(
            "Missing custom node: ComfyUI-AnimateDiff-Evolved\n"
            "  → Install via ComfyUI Manager or clone "
            "https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved"
        )

    vhs_node = base / "custom_nodes" / "ComfyUI-VideoHelperSuite"
    if not vhs_node.exists():
        issues.append(
            "Missing custom node: ComfyUI-VideoHelperSuite\n"
            "  → Install via ComfyUI Manager or clone "
            "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite"
        )

    return issues


def build(
    prompt: str,
    negative_prompt: str = DEFAULT_NEGATIVE,
    checkpoint: str = DEFAULT_CHECKPOINT,
    motion_module: str = DEFAULT_MOTION_MODULE,
    num_frames: int = 16,
    width: int = 512,
    height: int = 512,
    steps: int = 20,
    cfg: float = 7.5,
    seed: int = -1,
    sampler: str = "euler",
    scheduler: str = "linear",
    fps: int = 8,
    format: str = "gif",
    filename_prefix: str = "video",
    comfy_base: str | Path = None,
) -> dict:
    """
    Build an AnimateDiff video workflow dict.

    Args:
        prompt:        Text description of the animated scene.
        num_frames:    Number of frames to generate (8–32, multiples of 8).
        width/height:  Frame resolution (512x512 or 512x768 work well).
        steps:         Sampling steps.
        cfg:           Guidance scale.
        seed:          -1 for random.
        fps:           Frames per second in the output video.
        format:        Output format: "gif" or "mp4".
        motion_module: Filename in models/animatediff_models/.
        comfy_base:    Path to ComfyUI folder, used to verify setup files exist.
    """
    if comfy_base is not None:
        issues = check_setup(comfy_base)
        if issues:
            raise RuntimeError(
                "AnimateDiff setup incomplete:\n\n" + "\n\n".join(issues)
            )

    if seed == -1:
        seed = random.randint(0, 2**32 - 1)

    num_frames = max(8, (num_frames // 8) * 8)  # must be multiple of 8

    return {
        # Load checkpoint
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        # Load AnimateDiff motion module
        "2": {
            "class_type": "ADE_AnimateDiffLoaderWithContext",
            "inputs": {
                "model_name": motion_module,
                "beta_schedule": "linear",
                "model": ["1", 0],
            },
        },
        # Positive prompt
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["1", 1]},
        },
        # Negative prompt
        "4": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["1", 1]},
        },
        # Empty latent (batch_size = num_frames for AnimateDiff)
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": num_frames},
        },
        # KSampler with AnimateDiff evolved sampling
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler,
                "scheduler": scheduler,
                "denoise": 1.0,
                "model": ["2", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
            },
        },
        # Decode latents to pixels
        "7": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["6", 0], "vae": ["1", 2]},
        },
        # Combine frames into video
        "8": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["7", 0],
                "frame_rate": fps,
                "loop_count": 0,
                "filename_prefix": filename_prefix,
                "format": f"image/{format}",
                "save_output": True,
                "pingpong": False,
            },
        },
    }
