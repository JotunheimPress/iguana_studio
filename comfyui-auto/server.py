"""Iguana Studio's server-side functions, plus the two plain routes that are still HTTP.

Since the pytincture switch-over (PYTINCTURE_PLAN.md Phase 5) the page is `appcode/` and
the server is `service.py`. What lives here:
  * functions the BFFs call — list_checkpoints(), list_loras(), gallery(), delete_output(),
    list_prompts()/save_prompt()/delete_prompt() — plain functions, no routes;
  * routes that stay plain HTTP: GET /outputs/{f} (images belong in <img src>, not JSON),
    and the /debug tools. service.py copies them in front of pytincture's own routes.
The classic page (static/index.html) and its JSON routes (/generate, /job, /checkpoints,
/loras, /gallery, /prompts, /comfy-status) are gone. `python server.py` runs service.py.
"""

import sys
import json
import time
import threading
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import FileResponse

sys.path.insert(0, str(Path(__file__).parent))
import client
from workflows import text2img
from workflows.defaults import base_of

app = FastAPI(title="Iguana Studio")

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "outputs"
TEMP_DIR   = BASE_DIR / "temp"
# Durable app data (bind-mounted like outputs/, so it survives a rebuild). Not outputs/:
# that folder is the gallery, and a settings file has no business sitting in it.
DATA_DIR   = BASE_DIR / "data"
PROMPTS_FILE = DATA_DIR / "saved-prompts.json"

OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# What counts as a generated file — shared by /gallery and the delete endpoint so
# the two can't disagree about what's listable vs. deletable.
MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4"}

# ── routes ───────────────────────────────────────────────────────────────────

def list_checkpoints():
    """Return installed checkpoints as [{name, base}], sorted alphabetically.

    The base ships with each entry so the frontend can group the picker without
    re-deriving the classification from the filename — see defaults.base_of().
    """
    import requests as req
    try:
        r = req.get(f"{client.COMFY_URL}/object_info/CheckpointLoaderSimple", timeout=5)
        r.raise_for_status()
        names = r.json()["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        out = [{"name": n, "base": base_of(n)} for n in names]
    except Exception as e:
        return {"checkpoints": [], "error": str(e)}
    # GGUF FLUX diffusion models (models/unet) are pickable too: workflows/flux.py loads
    # a .gguf split, with the shared clip_l/t5xxl/ae files. Kontext is an edit model —
    # it lives in Edit mode, not in the text-to-image picker. Best-effort: no ComfyUI-GGUF
    # node simply means no GGUF entries.
    try:
        r = req.get(f"{client.COMFY_URL}/object_info/UnetLoaderGGUF", timeout=5)
        r.raise_for_status()
        ggufs = r.json()["UnetLoaderGGUF"]["input"]["required"]["unet_name"][0]
        out += [{"name": n, "base": "FLUX"} for n in ggufs
                if base_of(n) == "FLUX" and "kontext" not in n.lower()]
    except Exception:
        pass
    # Z-Image and FLUX.2 diffusion models (models/diffusion_models): UNETLoader lists them,
    # and workflows/zimage.py / flux2.py load them with their text encoder and VAE. Only
    # those names: the same list holds WAN, ACE-Step and others that are no text-to-image
    # model for this picker.
    try:
        r = req.get(f"{client.COMFY_URL}/object_info/UNETLoader", timeout=5)
        r.raise_for_status()
        unets = r.json()["UNETLoader"]["input"]["required"]["unet_name"][0]
        out += [{"name": n, "base": base_of(n)} for n in unets
                if base_of(n) in ("Z-Image", "FLUX.2")]
    except Exception:
        pass
    return {"checkpoints": sorted(out, key=lambda c: c["name"].lower())}


def list_loras():
    """Return LoRA filenames available in ComfyUI, sorted alphabetically.

    Same shape as /checkpoints: ComfyUI reports installed LoRAs as the enum of
    LoraLoader's lora_name input, so the node definition is the inventory.
    """
    import requests as req
    try:
        r = req.get(f"{client.COMFY_URL}/object_info/LoraLoader", timeout=5)
        r.raise_for_status()
        names = r.json()["LoraLoader"]["input"]["required"]["lora_name"][0]
        return {"loras": sorted(names)}
    except Exception as e:
        return {"loras": [], "error": str(e)}


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


def gallery():
    """Return all output files sorted newest-first."""
    files = []
    for p in OUTPUT_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in MEDIA_SUFFIXES:
            files.append({"name": p.name, "mtime": p.stat().st_mtime, "size": p.stat().st_size})
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return files


# ── gallery thumbnails ─────────────────────────────────────────────────────────
# Gallery tiles are 140 px; the outputs are 1024 px+ PNGs. Decoding those to draw tiles was
# the whole cost of the gallery's scroll stutter (PYTINCTURE_PLAN.md Phase 4: with image
# loads blocked both pages held 60 fps). So tiles load a small WebP, made on first request
# and cached next to the originals in outputs/.thumbs/ (hidden; gallery() lists files with a
# media suffix only). It survives rebuilds because outputs/ is a volume. Rebuilt when the
# source is newer; deleted with it. Videos keep their <video preload=metadata> tiles — the
# image has no ffmpeg, and those only fetch metadata anyway.
THUMB_DIR = OUTPUT_DIR / ".thumbs"
THUMB_PX = 280                  # short side: sharp at 2x on a 140 px cover-cropped tile
THUMB_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _thumb_file(src: Path) -> Path:
    return THUMB_DIR / (src.name + ".webp")


def thumb_path(filename: str) -> Path | None:
    """The cached thumbnail for an output image, made if missing or stale; None if the name
    isn't an image in outputs/. Raises if the image can't be decoded."""
    src = OUTPUT_DIR / Path(filename).name
    if src.suffix.lower() not in THUMB_SUFFIXES or not src.is_file():
        return None
    dst = _thumb_file(src)
    try:
        if dst.stat().st_mtime >= src.stat().st_mtime:
            return dst
    except OSError:
        pass                                            # not made yet
    from PIL import Image

    THUMB_DIR.mkdir(exist_ok=True)
    with Image.open(src) as im:
        im.draft("RGB", (THUMB_PX, THUMB_PX))           # JPEG: decode at reduced size
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
        scale = THUMB_PX / min(im.size)
        if scale < 1:                                   # cover: the SHORT side is THUMB_PX
            im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))),
                           Image.LANCZOS)
        # Atomic: two tiles asking at once each write their own temp file, last rename wins.
        tmp = dst.with_name(f"{dst.name}.{threading.get_ident()}.tmp")
        im.save(tmp, "WEBP", quality=80, method=4)
    tmp.replace(dst)
    return dst


def warm_thumbs(names=None) -> int:
    """Make any missing/stale thumbnails — for `names`, or every output newest first.
    Made on demand otherwise, which is 100+ ms each: a first fling through a big uncached
    gallery queued 1,400 of them behind the tiles actually in view. Warming means that path
    is rare: service.py runs this once in the background at start, and jobs.py runs it for
    each new output as its job finishes. Never raises."""
    if names is None:
        try:
            names = [f["name"] for f in gallery()]
        except OSError:
            return 0
    made = 0
    for name in names:
        try:
            src = OUTPUT_DIR / Path(name).name
            dst = _thumb_file(src)
            if src.suffix.lower() in THUMB_SUFFIXES and (
                    not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime):
                thumb_path(name)
                made += 1
        except Exception:  # noqa: BLE001 - one bad file must not stop the rest
            pass
    return made


@app.get("/thumbs/{filename}")
def get_thumb(filename: str, v: str = ""):
    """A gallery tile's image. With ?v=<mtime> (what the gallery sends) it is cacheable for
    good — a changed file gets a new v. A file Pillow can't read falls back to the original."""
    try:
        path = thumb_path(filename)
    except Exception:  # noqa: BLE001 - corrupt/odd image: the tile still shows something
        path = OUTPUT_DIR / Path(filename).name
        if not path.is_file():
            path = None
        else:
            return FileResponse(path)
    if path is None:
        raise HTTPException(status_code=404, detail="No such image")
    return FileResponse(path, media_type="image/webp", headers={
        "Cache-Control": "public, max-age=31536000, immutable" if v else "no-cache"})


@app.get("/outputs/{filename}")
def get_output(filename: str):
    # Prevent path traversal — only serve files directly in outputs/
    path = OUTPUT_DIR / Path(filename).name
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


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
    _thumb_file(path).unlink(missing_ok=True)           # its gallery thumbnail goes too
    return {"deleted": path.name}


# ── entry point ──────────────────────────────────────────────────────────────


# ── saved prompts ────────────────────────────────────────────────────────────
# A saved prompt is the sidebar: the manual text, the modifier dropdowns, and the
# negative prompt — keyed by a name the user picks. Not the checkpoint, LoRAs or
# sampler numbers: those belong to a mode, and reloading a prompt shouldn't silently
# swap the model out from under it. Stored server-side rather than in localStorage so
# they outlive a cleared browser and are the same in every browser.
# The page decides which field ids exist; the server only bounds sizes and shapes.
_prompts_lock = threading.Lock()
PROMPT_NAME_MAX = 80
PROMPT_FIELD_MAX = 4000
PROMPT_FIELDS_MAX = 40


def _read_prompts() -> list[dict]:
    try:
        data = json.loads(PROMPTS_FILE.read_text())
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _write_prompts(items: list[dict]) -> None:
    # Atomic: a torn write would lose every saved prompt, not just the new one.
    tmp = PROMPTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=1))
    tmp.replace(PROMPTS_FILE)


def list_prompts():
    """Saved prompts, most recently saved first."""
    return {"prompts": sorted(_read_prompts(), key=lambda p: p.get("saved", 0), reverse=True)}


def save_prompt(body: dict):
    """Save (or overwrite, by name) one prompt: {name, fields: {id: value}}."""
    name = str(body.get("name") or "").strip()
    fields = body.get("fields")
    if not name or len(name) > PROMPT_NAME_MAX:
        raise HTTPException(status_code=400, detail=f"A name is required (up to {PROMPT_NAME_MAX} characters).")
    if not isinstance(fields, dict) or len(fields) > PROMPT_FIELDS_MAX:
        raise HTTPException(status_code=400, detail="fields must be an object of field id → value.")
    clean = {}
    for k, v in fields.items():
        if not isinstance(k, str) or not isinstance(v, str) or len(k) > 40 or len(v) > PROMPT_FIELD_MAX:
            raise HTTPException(status_code=400, detail=f"Bad field: {str(k)[:40]!r}")
        clean[k] = v
    entry = {"name": name, "fields": clean, "saved": time.time()}
    with _prompts_lock:
        items = [p for p in _read_prompts() if p.get("name") != name]
        items.append(entry)
        _write_prompts(items)
    return {"ok": True, "prompt": entry}


def delete_prompt(name: str):
    with _prompts_lock:
        items = _read_prompts()
        kept = [p for p in items if p.get("name") != name]
        if len(kept) == len(items):
            raise HTTPException(status_code=404, detail="No saved prompt by that name.")
        _write_prompts(kept)
    return {"ok": True}


if __name__ == "__main__":
    # Kept for muscle memory: the server is service.py now (pytincture + these routes).
    import runpy

    runpy.run_path(str(BASE_DIR / "service.py"), run_name="__main__")
