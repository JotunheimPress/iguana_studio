"""FastAPI web GUI for ComfyUI automation."""

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
from workflows import text2img, img2img, video, photomaker

app = FastAPI(title="ComfyUI Automation")

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "outputs"
TEMP_DIR   = BASE_DIR / "temp"
STATIC_DIR = BASE_DIR / "static"
COMFY_BASE = Path("C:/Users/blade/Documents/ComfyUI")

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

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
        elif task == "video":
            workflow = video.build(**params, comfy_base=COMFY_BASE)
        elif task == "photomaker":
            workflow = photomaker.build(image_paths=image_paths, **params)
        else:
            raise ValueError(f"Unknown task: {task}")

        paths = client.run_workflow(workflow, save_dir=OUTPUT_DIR)
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
    frames: int = Form(16),
    fps: int = Form(8),
    fmt: str = Form("gif"),
    pm_width: int = Form(1024),
    pm_height: int = Form(1024),
    pm_model: str = Form("photomaker-v2.bin"),
    image: Optional[UploadFile] = File(None),
    images: list[UploadFile] = File(default=[]),
):
    if task == "img2img" and (not image or not image.filename):
        raise HTTPException(status_code=400, detail="An image is required for Edit Image.")
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
    elif task == "video":
        params = dict(
            prompt=prompt,
            negative_prompt=negative or video.DEFAULT_NEGATIVE,
            num_frames=frames, width=width, height=height,
            steps=steps, cfg=cfg, seed=seed, fps=fps, format=fmt,
        )
    elif task == "photomaker":
        params = dict(
            prompt=prompt,
            negative_prompt=negative or photomaker.DEFAULT_NEGATIVE,
            width=pm_width, height=pm_height, steps=steps, cfg=cfg, seed=seed,
            photomaker_model=pm_model,
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


@app.get("/debug/nodes")
def debug_nodes():
    """List all node class names ComfyUI knows about."""
    import requests as req
    try:
        r = req.get(f"http://localhost:{client.COMFY_PORT}/object_info", timeout=5)
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
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4"}:
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


# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("ComfyUI Automation GUI starting...")
    print("Open http://localhost:7860 in your browser\n")
    uvicorn.run("server:app", host="0.0.0.0", port=7860, reload=False)
