"""Iguana Studio's server: the pytincture page at /iguana/ (`/` redirects there).

One process, one FastAPI app. pytincture builds it; the few plain routes (`/upload`,
`/api/health`, and server.py's `/outputs/{f}` + `/debug/*`) go IN FRONT of pytincture's
own, because pytincture registers a catch-all `/{application}` that would otherwise swallow
one-segment paths. History: PYTINCTURE_PLAN.md (the classic page was deleted in Phase 5).

Plain routes, not BFF, for binary: `POST /upload` stores files into temp/ and hands back
ids the BFF's generate() takes — photos are megabytes, and the BFF is JSON.

Loopback only: `allowed_hosts` answers any other Host with 400, and there is no login.
"""
from __future__ import annotations

import os
import re
import sys
import time
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
APPCODE = BASE_DIR / "appcode"
# BFF modules import `services.*`, `workflows.*` and `client` from the repo root, and must
# share THIS process's modules (the job table) — so the root goes on sys.path first.
sys.path.insert(0, str(BASE_DIR))


from fastapi import File, HTTPException, UploadFile  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pytincture import PytinctureConfig, create_app  # noqa: E402

import server as classic  # noqa: E402  (server-side functions + /outputs and /debug routes)

APPLICATION = "iguana"
HOST = os.environ.get("IGUANA_HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "7862"))
TEMP_DIR = BASE_DIR / "temp"
UPLOAD_MAX = 40 * 1024 * 1024
UPLOAD_ID = re.compile(r"^up-[0-9a-f]{32}\.(png|jpe?g|webp)$")
UPLOAD_TTL = 3600            # an upload no job consumed is swept after an hour


def upload_path(upload_id: str) -> Path | None:
    """temp/ path for an id from POST /upload, or None. The BFF resolves ids through
    here, so a request can only ever name a file this route wrote."""
    if not UPLOAD_ID.match(upload_id or ""):
        return None
    p = TEMP_DIR / upload_id
    return p if p.is_file() else None


def upload_from_output(name: str) -> str | None:
    """Copy outputs/<name> into temp/ as an upload id, or None if it isn't a usable image.

    "Send to Refine/Edit/Animate" from the gallery uses this, so a job never reads
    outputs/ directly: jobs DELETE their source when they finish, and that must be a copy.
    The name is reduced to a basename and must be an image already in outputs/.
    """
    import shutil

    from services.jobs import OUTPUT_DIR

    if not name or name != Path(name).name:
        return None
    src = OUTPUT_DIR / name
    suffix = src.suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".webp") or not src.is_file():
        return None
    _sweep_uploads()
    upload_id = f"up-{uuid.uuid4().hex}{suffix}"
    shutil.copyfile(src, TEMP_DIR / upload_id)
    return upload_id


def _sweep_uploads() -> None:
    now = time.time()
    for p in TEMP_DIR.glob("up-*"):
        try:
            if now - p.stat().st_mtime > UPLOAD_TTL:
                p.unlink(missing_ok=True)
        except OSError:
            pass


def build_app():
    app = create_app(PytinctureConfig(
        modules_path=str(APPCODE),
        default_application=APPLICATION,
        allowed_hosts=("127.0.0.1", "localhost", "::1"),
        cookie_namespace="iguana",
        # pytincture caps EVERY request body at 16 MiB, ahead of any route — an 18 MB photo
        # was refused before reaching /upload. The env var MAX_REQUEST_BODY_BYTES does NOT
        # change it (the config's own default wins); this field does. 48 MiB = one UPLOAD_MAX
        # file plus multipart overhead; the page uploads one file per request.
        max_request_body_bytes=48 * 1024 * 1024,
    ))

    # The page's stylesheet.
    app.mount("/istatic", StaticFiles(directory=str(APPCODE / "static")), name="istatic")

    extra = []

    async def health():
        return {"ok": True}

    async def upload(files: list[UploadFile] = File(...)):
        """Store uploads in temp/ and return their ids, in order."""
        _sweep_uploads()
        ids = []
        for f in files:
            suffix = (Path(f.filename or "").suffix or ".png").lower()
            if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
                raise HTTPException(status_code=400, detail=f"{f.filename}: not an image")
            upload_id = f"up-{uuid.uuid4().hex}{suffix}"
            dest = TEMP_DIR / upload_id
            size = 0
            with open(dest, "wb") as out:
                while chunk := await f.read(1 << 20):
                    size += len(chunk)
                    if size > UPLOAD_MAX:
                        out.close()
                        dest.unlink(missing_ok=True)
                        raise HTTPException(status_code=413, detail=f"{f.filename}: over 40 MB")
                    out.write(chunk)
            ids.append(upload_id)
        return {"ids": ids}

    extra.append(APIRoute("/api/health", health, methods=["GET"]))
    extra.append(APIRoute("/upload", upload, methods=["POST"]))

    # server.py's routes + ours ahead of pytincture's catch-alls. Only APIRoutes: its own
    # /docs and /openapi.json would clash with pytincture's.
    classic_routes = [r for r in classic.app.routes
                      if isinstance(r, APIRoute) and not r.path.startswith(("/docs", "/openapi"))]
    app.router.routes[0:0] = extra + classic_routes
    return app


app = build_app()

# Fill in any missing gallery thumbnails once, in the background (server.warm_thumbs).
import threading  # noqa: E402

threading.Thread(target=classic.warm_thumbs, name="warm-thumbs", daemon=True).start()


if __name__ == "__main__":
    import uvicorn

    TEMP_DIR.mkdir(exist_ok=True)
    print(f"\n  Iguana Studio → http://localhost:{PORT}/\n")
    uvicorn.run(app, host=HOST, port=PORT)
