"""Generation jobs — shared by the classic page (server.py) and the pytincture page.

A plain module on purpose: pytincture re-executes BFF modules on every call, so the job
table, the threads and the phase map must live somewhere that stays loaded. Both pages
run in the same process and see the same JOBS.

Each job runs in a daemon thread (client.py is sync: requests + websocket-client) and only
ever writes whole values into its dict, so readers on other threads never see a torn update.
"""
from __future__ import annotations

import time
import threading
import uuid
from pathlib import Path
from typing import Optional

import client
from workflows import text2img, img2img, video, photomaker, kontext

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "outputs"

# A 121-frame WAN clip runs well past the 600 s client default, and a job that finished
# but got reported as a timeout is the worst of both outcomes — it burned the GPU time and
# threw the result away. Video tasks get their own budget.
VIDEO_TIMEOUT = 1800
VIDEO_TASKS = {"img2vid", "video"}

# ComfyUI names the running node; the browser wants a phase. Keyed by class_type, which
# the workflow dict already carries, so this works for every task without each builder
# having to describe itself. Unknown classes fall through to their own name — wrong-looking
# is better than a blank status bar with no clue what it is doing.
PHASES = {
    "UNETLoader": "loading model", "UnetLoaderGGUF": "loading model",
    "CheckpointLoaderSimple": "loading model", "ImageOnlyCheckpointLoader": "loading model",
    "CLIPLoader": "loading text encoder", "DualCLIPLoader": "loading text encoder",
    "VAELoader": "loading VAE",
    "LoraLoader": "applying LoRA",
    "ModelSamplingFlux": "preparing model",
    "PhotoMakerLoaderPlus": "loading PhotoMaker", "PhotoMakerInsightFaceLoader": "loading face detector",
    "PhotoMakerEncodePlus": "reading the reference faces",
    "CLIPTextEncode": "encoding prompt", "CLIPTextEncodeSDXL": "encoding prompt",
    "CLIPTextEncodeFlux": "encoding prompt",
    "LoadImage": "reading source image", "VAEEncode": "encoding source image",
    "Wan22ImageToVideoLatent": "preparing frames",
    "KSampler": "sampling", "SamplerCustom": "sampling",
    "VAEDecode": "decoding", "CreateVideo": "encoding video",
    "SaveVideo": "saving", "SaveImage": "saving",
}

jobs: dict[str, dict] = {}


# ── background job runner ────────────────────────────────────────────────────

def _run(
    job_id: str,
    task: str,
    params: dict,
    image_path: Optional[Path] = None,
    image_paths: Optional[list[Path]] = None,
):
    JOBS[job_id]["status"] = "running"
    try:
        if task == "text2img":
            workflow = text2img.build(**params)
        elif task == "img2img":
            workflow = img2img.build(image_path=image_path, **params)
        elif task == "img2vid":
            workflow = video.build_i2v(image_path=image_path, **params)
        elif task == "video":
            workflow = video.build_t2v(**params)
        elif task == "photomaker":
            workflow = photomaker.build(image_paths=image_paths, **params)
        elif task == "kontext":
            workflow = kontext.build(image_path=image_path, **params)
        else:
            raise ValueError(f"Unknown task: {task}")

        job = JOBS[job_id]

        def on_progress(value, maximum, node):
            """Called from the websocket watcher. Only ever writes whole values into the
            job dict — the poll route reads it from another thread and a half-updated
            progress block would render as a bar jumping backwards."""
            if node is not None:
                cls = (workflow.get(str(node)) or {}).get("class_type", "")
                job["phase"] = PHASES.get(cls, cls or "working")
            if value is None or not maximum:
                return
            # Timing starts at the first step SEEN, and records the step number as well as
            # the time. ComfyUI throttles these messages, so the first one can already say
            # "step 18" — anchoring on time alone then divides a near-zero elapsed by 18
            # and reports 0s remaining for the rest of the run.
            if job.get("step_t0") is None:
                job["step_t0"] = (time.time(), int(value))
            job["progress"] = {"value": int(value), "max": int(maximum)}

        timeout = VIDEO_TIMEOUT if task in VIDEO_TASKS else 600
        paths = client.run_workflow(workflow, save_dir=OUTPUT_DIR, timeout=timeout,
                                    on_progress=on_progress)
        JOBS[job_id].update(status="done", files=[p.name for p in paths])
    except Exception as e:
        JOBS[job_id].update(status="error", message=str(e))
    finally:
        if image_path and image_path.exists():
            image_path.unlink(missing_ok=True)
        for p in (image_paths or []):
            if p.exists():
                p.unlink(missing_ok=True)




JOBS: dict[str, dict] = {}


def new_id() -> str:
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "pending", "files": [], "message": "",
                    "phase": "queued", "progress": None, "step_t0": None,
                    "created": time.time()}
    return job_id


def start(job_id: str, task: str, params: dict, image_path: Optional[Path] = None,
          image_paths: Optional[list[Path]] = None) -> None:
    threading.Thread(target=_run, args=(job_id, task, params, image_path, image_paths),
                     daemon=True).start()


def params_for(task: str, f: dict) -> dict:
    """Builder kwargs for a task from the form fields (shared by both pages)."""
    if task == "text2img":
        params = dict(
            prompt=f['prompt'],
            negative_prompt=f['negative'] or text2img.DEFAULT_NEGATIVE,
            checkpoint=f['checkpoint'],
            width=f['width'], height=f['height'], steps=f['steps'], cfg=f['cfg'], seed=f['seed'],
            loras=f['loras'],
        )
    elif task == "img2img":
        params = dict(
            prompt=f['prompt'],
            negative_prompt=f['negative'] or img2img.DEFAULT_NEGATIVE,
            checkpoint=f['checkpoint'],
            denoise=f['denoise'], steps=f['steps'], cfg=f['cfg'], seed=f['seed'],
            loras=f['loras'],
        )
    elif task in VIDEO_TASKS:
        # img2vid and video take identical params — the only difference is the source
        # image, which rides the same upload path as img2img and is applied by the
        # dispatcher, not here.
        params = dict(
            prompt=f['prompt'],
            negative_prompt=f['negative'] or video.DEFAULT_NEGATIVE,
            width=f['width'], height=f['height'], length=f['length'],
            steps=f['steps'], cfg=f['cfg'], seed=f['seed'], fps=f['fps'], shift=f['shift'],
        )
    elif task == "photomaker":
        params = dict(
            prompt=f['prompt'],
            negative_prompt=f['negative'] or photomaker.DEFAULT_NEGATIVE,
            width=f['pm_width'], height=f['pm_height'], steps=f['steps'], cfg=f['cfg'], seed=f['seed'],
            photomaker_model=f['pm_model'],
            loras=f['loras'],
        )
    elif task == "kontext":
        # No negative prompt, no width/height and no denoise: Kontext zeroes its own
        # negative, and the output size is derived from the source by
        # FluxKontextImageScale. Guidance rides in on the `cfg` field so the frontend
        # can reuse the existing slider — it is NOT sampler CFG, which is pinned to 1.
        params = dict(
            prompt=f['prompt'],
            guidance=f['cfg'],
            steps=f['steps'],
            seed=f['seed'],
        )
    else:
        params = {}
    return params


def view(job_id: str) -> dict:
    """Job state, plus a step counter and an ETA while it is sampling.

    The ETA is measured, not modelled: elapsed-per-completed-step extrapolated over the
    steps left, timed from the first step SEEN (ComfyUI throttles progress messages, so
    the first one can already say "step 18"). No ETA until a second step arrives.
    """
    job = JOBS.get(job_id)
    if job is None:
        return {"status": "not_found"}
    out = {k: v for k, v in job.items() if k != "step_t0"}
    p, anchor = job.get("progress"), job.get("step_t0")
    if p and anchor and p["max"] > p["value"]:
        t0, v0 = anchor
        done = p["value"] - v0
        if done > 0:
            per_step = (time.time() - t0) / done
            out["eta"] = int(per_step * (p["max"] - p["value"]))
    return out
