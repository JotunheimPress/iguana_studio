"""FastAPI web GUI for ComfyUI automation."""

import os
import sys
import uuid
import shutil
import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, Form, File, HTTPException
from fastapi.responses import FileResponse
import uvicorn

sys.path.insert(0, str(Path(__file__).parent))
import client
from workflows import text2img, img2img, video, photomaker, kontext

app = FastAPI(title="Iguana Studio")

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "outputs"
TEMP_DIR   = BASE_DIR / "temp"
STATIC_DIR = BASE_DIR / "static"

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

# What counts as a generated file — shared by /gallery and the delete endpoint so
# the two can't disagree about what's listable vs. deletable.
MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4"}

# A 121-frame WAN clip runs well past the 600 s client default, and a job that finished
# but got reported as a timeout is the worst of both outcomes — it burned the GPU time and
# threw the result away. Video tasks get their own budget.
VIDEO_TIMEOUT = 1800
VIDEO_TASKS = {"img2vid", "video"}

jobs: dict[str, dict] = {}


# ── background job runner ────────────────────────────────────────────────────

def _run_job(
    job_id: str,
    task: str,
    params: dict,
    image_path: Optional[Path] = None,
    image_paths: Optional[list[Path]] = None,
):
    jobs[job_id]["status"] = "running"
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

        timeout = VIDEO_TIMEOUT if task in VIDEO_TASKS else 600
        paths = client.run_workflow(workflow, save_dir=OUTPUT_DIR, timeout=timeout)
        jobs[job_id].update(status="done", files=[p.name for p in paths])
    except Exception as e:
        jobs[job_id].update(status="error", message=str(e))
    finally:
        if image_path and image_path.exists():
            image_path.unlink(missing_ok=True)
        for p in (image_paths or []):
            if p.exists():
                p.unlink(missing_ok=True)


# ── routes ───────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/comfy-status")
def comfy_status():
    return {"running": client.is_running()}


@app.post("/generate")
async def generate(
    task: str = Form(...),
    prompt: str = Form(...),
    negative: str = Form(""),
    checkpoint: str = Form("sd_xl_base_1.0.safetensors"),
    width: int = Form(1024),
    height: int = Form(1024),
    steps: int = Form(25),
    cfg: float = Form(7.0),
    seed: int = Form(-1),
    denoise: float = Form(0.75),
    length: int = Form(49),
    fps: int = Form(24),
    shift: float = Form(8.0),
    pm_width: int = Form(1024),
    pm_height: int = Form(1024),
    pm_model: str = Form("photomaker-v2.bin"),
    image: Optional[UploadFile] = File(None),
    images: list[UploadFile] = File(default=[]),
):
    if task in ("img2img", "kontext", "img2vid") and (not image or not image.filename):
        raise HTTPException(status_code=400, detail="A source image is required for this mode.")
    if task == "photomaker" and not any(f.filename for f in images):
        raise HTTPException(status_code=400, detail="At least one reference photo is required.")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "pending", "files": [], "message": ""}

    # Single image (img2img)
    image_path = None
    if image and image.filename:
        suffix = Path(image.filename).suffix or ".png"
        image_path = TEMP_DIR / f"{job_id}{suffix}"
        with open(image_path, "wb") as f:
            shutil.copyfileobj(image.file, f)

    # Multiple images (photomaker)
    image_paths = []
    for i, upload in enumerate(images):
        if upload.filename:
            suffix = Path(upload.filename).suffix or ".png"
            p = TEMP_DIR / f"{job_id}_{i}{suffix}"
            with open(p, "wb") as f:
                shutil.copyfileobj(upload.file, f)
            image_paths.append(p)

    if task == "text2img":
        params = dict(
            prompt=prompt,
            negative_prompt=negative or text2img.DEFAULT_NEGATIVE,
            checkpoint=checkpoint,
            width=width, height=height, steps=steps, cfg=cfg, seed=seed,
        )
    elif task == "img2img":
        params = dict(
            prompt=prompt,
            negative_prompt=negative or img2img.DEFAULT_NEGATIVE,
            checkpoint=checkpoint,
            denoise=denoise, steps=steps, cfg=cfg, seed=seed,
        )
    elif task in VIDEO_TASKS:
        # img2vid and video take identical params — the only difference is the source
        # image, which rides the same upload path as img2img and is applied by the
        # dispatcher, not here.
        params = dict(
            prompt=prompt,
            negative_prompt=negative or video.DEFAULT_NEGATIVE,
            width=width, height=height, length=length,
            steps=steps, cfg=cfg, seed=seed, fps=fps, shift=shift,
        )
    elif task == "photomaker":
        params = dict(
            prompt=prompt,
            negative_prompt=negative or photomaker.DEFAULT_NEGATIVE,
            width=pm_width, height=pm_height, steps=steps, cfg=cfg, seed=seed,
            photomaker_model=pm_model,
        )
    elif task == "kontext":
        # No negative prompt, no width/height and no denoise: Kontext zeroes its own
        # negative, and the output size is derived from the source by
        # FluxKontextImageScale. Guidance rides in on the `cfg` field so the frontend
        # can reuse the existing slider — it is NOT sampler CFG, which is pinned to 1.
        params = dict(
            prompt=prompt,
            guidance=cfg,
            steps=steps,
            seed=seed,
        )
    else:
        params = {}

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, task, params, image_path, image_paths or None),
        daemon=True,
    )
    thread.start()
    return {"job_id": job_id}


@app.get("/job/{job_id}")
def get_job(job_id: str):
    return jobs.get(job_id, {"status": "not_found"})


@app.get("/checkpoints")
def list_checkpoints():
    """Return checkpoint filenames available in ComfyUI, sorted alphabetically."""
    import requests as req
    try:
        r = req.get(f"{client.COMFY_URL}/object_info/CheckpointLoaderSimple", timeout=5)
        r.raise_for_status()
        names = r.json()["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        return {"checkpoints": sorted(names)}
    except Exception as e:
        return {"checkpoints": [], "error": str(e)}


@app.get("/debug/nodes")
def debug_nodes():
    """List all node class names ComfyUI knows about."""
    import requests as req
    try:
        r = req.get(f"{client.COMFY_URL}/object_info", timeout=5)
        return {"nodes": sorted(r.json().keys())}
    except Exception as e:
        return {"error": str(e)}


@app.post("/debug/workflow")
async def debug_workflow(
    task: str = Form(...),
    prompt: str = Form("a test prompt img"),
):
    """Dry-run a minimal workflow and return what would be sent + any error."""
    import json
    try:
        if task == "text2img":
            wf = text2img.build(prompt=prompt)
        elif task == "photomaker":
            wf = {"error": "photomaker needs images — test via the GUI"}
        else:
            wf = {"error": f"use task=text2img for quick test"}
        return {"workflow": wf}
    except Exception as e:
        return {"error": str(e)}


@app.get("/gallery")
def gallery():
    """Return all output files sorted newest-first."""
    files = []
    for p in OUTPUT_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in MEDIA_SUFFIXES:
            files.append({"name": p.name, "mtime": p.stat().st_mtime, "size": p.stat().st_size})
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files


@app.get("/outputs/{filename}")
def get_output(filename: str):
    # Prevent path traversal — only serve files directly in outputs/
    path = OUTPUT_DIR / Path(filename).name
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


@app.delete("/outputs/{filename}")
def delete_output(filename: str):
    """Delete one generated file. Irreversible — there is no trash."""
    # Same Path(filename).name guard as the GET: strip any directory part so a
    # crafted name can't reach outside outputs/.
    path = OUTPUT_DIR / Path(filename).name
    # Only ever delete generated media, never anything else that lands in here.
    if path.suffix.lower() not in MEDIA_SUFFIXES:
        raise HTTPException(status_code=400, detail="Not a generated media file")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    try:
        path.unlink()
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not delete: {e}")
    return {"deleted": path.name}


# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "7862"))
    print("Iguana Studio starting...")
    print(f"Open http://localhost:{port} in your browser\n")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
