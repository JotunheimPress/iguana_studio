"""PuLID-FLUX — FLUX.1 images of a specific person, from reference photos (Person mode).

PuLID extracts the identity from the references and injects it into FLUX's attention
blocks while sampling. The prompt stays an ordinary FLUX prompt: there is no trigger word,
and the subject's face comes from the photos, not the text.

How the identity is read (all inside ApplyPulidFlux):
  - InsightFace antelopev2 finds the face and gives an ArcFace identity embedding;
  - the face is aligned, its background masked out by a face-parsing model (facexlib), and
    encoded by EVA02-CLIP-L-14-336 for the finer detail ArcFace leaves out;
  - PuLID's IDFormer turns both into ID tokens, which cross-attend into FLUX's blocks.
With several photos, each one is analysed and the ID tokens are combined. A photo with no
face found is skipped with a warning in ComfyUI's log; if none has a face the job fails.

The graph is the FLUX text-to-image graph (workflows/flux.py) with the model routed through
ApplyPulidFlux before ModelSamplingFlux. LoRAs are spliced in afterwards by lora.apply, which
repoints every consumer of the loader's MODEL edge — ApplyPulidFlux included — at the end
of the LoRA chain, so the order is loader → LoRAs → PuLID → shift → sampler.

Needs the ComfyUI_PuLID_Flux_ll custom node (lldacing) and its models — see the project
CLAUDE.md. PuLID-FLUX was trained on FLUX.1-dev; schnell runs but holds the likeness worse.
"""

import random
from pathlib import Path

from client import upload_image
from workflows import flux

DEFAULT_CHECKPOINT = "flux1-dev-Q8_0.gguf"
PULID_MODEL = "pulid_flux_v0.9.1.safetensors"

# InsightFace execution provider. "CPU" because the ComfyUI images ship the CPU build of
# onnxruntime (ai-stack/comfyui/Containerfile explains why). Face detection runs a few
# passes per reference photo — seconds at most, next to the diffusion.
INSIGHTFACE_PROVIDER = "CPU"

# Every reference is letterboxed onto this square before batching. ImageBatch would
# otherwise stretch each photo to the first one's size, distorting the faces it reads.
REF_SIZE = 1024

# Upper bound on reference photos: each costs a detection pass and adds ID tokens, and
# past a handful the likeness stops improving.
MAX_REFS = 8


def build(
    image_paths: list[str | Path],
    prompt: str,
    checkpoint: str = DEFAULT_CHECKPOINT,
    width: int = 1024,
    height: int = 1024,
    steps: int = -1,                 # -1 = auto from the model (dev 20, schnell 4)
    guidance: float = -1,            # -1 = auto (dev 3.5, schnell 1.0)
    seed: int = -1,
    weight: float = 1.0,             # identity strength
    start_at: float = 0.0,           # fraction of sampling where PuLID switches on
    end_at: float = 1.0,             # … and off
    filename_prefix: str = "pulid",
    loras=None,
) -> dict:
    """A PuLID-FLUX workflow. `image_paths` are local reference photos (1–8)."""
    if not image_paths:
        raise ValueError("At least one reference photo is required.")
    if len(image_paths) > MAX_REFS:
        raise ValueError(f"At most {MAX_REFS} reference photos.")
    if not 0.0 <= start_at < end_at <= 1.0:
        raise ValueError("Identity start must be below its end, both between 0 and 1.")

    if seed == -1:
        seed = random.randint(0, 2**32 - 1)

    # The FLUX text-to-image graph, LoRAs left out until PuLID is wired in.
    workflow = flux.build(prompt, checkpoint=checkpoint, width=width, height=height,
                          steps=steps, cfg=guidance, seed=seed,
                          filename_prefix=filename_prefix, loras=None)

    names = [upload_image(p) for p in image_paths]
    workflow.update(_reference_nodes(names))
    workflow.update({
        "p_model": {"class_type": "PulidFluxModelLoader", "inputs": {"pulid_file": PULID_MODEL}},
        "p_face": {"class_type": "PulidFluxInsightFaceLoader",
                   "inputs": {"provider": INSIGHTFACE_PROVIDER}},
        "p_eva": {"class_type": "PulidFluxEvaClipLoader", "inputs": {}},
        "p_apply": {
            "class_type": "ApplyPulidFlux",
            "inputs": {
                "model": ["1", 0],
                "pulid_flux": ["p_model", 0],
                "eva_clip": ["p_eva", 0],
                "face_analysis": ["p_face", 0],
                "image": [_last_ref_id(len(names)), 0],
                "weight": float(weight),
                "start_at": float(start_at),
                "end_at": float(end_at),
            },
        },
    })
    # ModelSamplingFlux ("5") now reads the identity-patched model.
    workflow["5"]["inputs"]["model"] = ["p_apply", 0]
    return flux._apply_loras(workflow, checkpoint, loras)


def _reference_nodes(names: list[str]) -> dict:
    """LoadImage → ResizeAndPadImage per photo, then an ImageBatch chain over them."""
    nodes = {}
    for i, name in enumerate(names):
        nodes[f"ref_{i}"] = {"class_type": "LoadImage", "inputs": {"image": name}}
        nodes[f"pad_{i}"] = {
            "class_type": "ResizeAndPadImage",
            "inputs": {"image": [f"ref_{i}", 0], "target_width": REF_SIZE,
                       "target_height": REF_SIZE, "padding_color": "white",
                       "interpolation": "lanczos"},
        }
    for i in range(1, len(names)):
        prev = ["pad_0", 0] if i == 1 else [f"batch_{i - 1}", 0]
        nodes[f"batch_{i}"] = {"class_type": "ImageBatch",
                               "inputs": {"image1": prev, "image2": [f"pad_{i}", 0]}}
    return nodes


def _last_ref_id(n: int) -> str:
    return "pad_0" if n == 1 else f"batch_{n - 1}"
