"""BFF for the generation side: models, jobs, and the job progress stream.

pytincture re-executes this module on every call, so it holds nothing: jobs live in
`services.jobs` (a plain module), and everything is imported inside methods.

`follow()` is the progress stream. pytincture caps a stream at BFF_STREAM_MAX_SECONDS (300)
and BFF_STREAM_IDLE_TIMEOUT_SECONDS (30), and an Animate job runs up to 30 min with silent
model loads. So the stream (a) sends the job's state whenever it changes and a heartbeat at
least every HEARTBEAT seconds, and (b) ends itself after a budget with `{"type": "continue"}`;
the page then calls follow() again. The job doesn't care: the stream is only a view of it.
That also means a page reload can pick a running job back up by id.
"""
from __future__ import annotations

import os

from pytincture.dataclass import backend_for_frontend, bff_stream

TASKS = ("text2img", "img2img", "photomaker", "kontext", "img2vid", "video")


@backend_for_frontend
class Studio:
    def checkpoints(self) -> dict:
        """Installed models as [{name, base, config}] — config is what an explicit model
        change stamps into the steps/CFG/size boxes (services.models)."""
        import server
        from services import models
        from workflows.defaults import NEGATIVE

        r = server.list_checkpoints()
        items = [{**c, "config": models.config_for(c["name"], c["base"])}
                 for c in r.get("checkpoints") or []]
        return {"ok": not r.get("error"), "checkpoints": items, "error": r.get("error"),
                "negative": NEGATIVE}

    def loras(self) -> dict:
        import server

        r = server.list_loras()
        return {"ok": not r.get("error"), "loras": r.get("loras") or [], "error": r.get("error")}

    def comfy_status(self) -> dict:
        import client

        return {"ok": True, "running": bool(client.is_running())}

    def generate(self, task: str, fields: dict, upload_ids: list | None = None) -> dict:
        """Start a job. `upload_ids` come from POST /upload — never paths."""
        import service
        from services import jobs

        if task not in TASKS:
            return {"ok": False, "error": f"unknown task: {task!r}"}
        paths = []
        for uid in upload_ids or []:
            p = service.upload_path(str(uid))
            if p is None:
                return {"ok": False, "error": "an uploaded image has expired — add it again"}
            paths.append(p)
        if task in ("img2img", "kontext", "img2vid") and len(paths) != 1:
            return {"ok": False, "error": "this mode needs one source image"}
        if task == "photomaker" and not paths:
            return {"ok": False, "error": "add at least one reference photo"}
        f = {"prompt": "", "negative": "", "checkpoint": "", "width": 1024, "height": 1024,
             "steps": 25, "cfg": 7.0, "seed": -1, "denoise": 0.75, "length": 81, "fps": 24,
             "shift": 8.0, "pm_width": 1024, "pm_height": 1024, "pm_model": "photomaker-v2.bin",
             "loras": []}
        if not isinstance((fields or {}).get("loras", []), list):
            return {"ok": False, "error": "loras must be a list"}
        f.update({k: v for k, v in (fields or {}).items() if k in f})
        # The classic route had FastAPI's Form() coercion; JSON doesn't, so do it here.
        try:
            for k in ("width", "height", "steps", "seed", "length", "fps", "pm_width", "pm_height"):
                f[k] = int(float(f[k]))
            for k in ("cfg", "denoise", "shift"):
                f[k] = float(f[k])
        except (TypeError, ValueError):
            return {"ok": False, "error": f"{k} must be a number"}
        for k in ("prompt", "negative", "checkpoint", "pm_model"):
            f[k] = str(f[k] or "")
        try:
            params = jobs.params_for(task, f)
        except (KeyError, ValueError, TypeError) as exc:
            return {"ok": False, "error": str(exc)}
        job_id = jobs.new_id()
        single = paths[0] if task != "photomaker" and paths else None
        jobs.start(job_id, task, params, single, paths if task == "photomaker" else None)
        return {"ok": True, "job_id": job_id}

    def from_output(self, name: str) -> dict:
        """An upload id for an image already in outputs/ (gallery → Refine/Edit/Animate)."""
        import service

        upload_id = service.upload_from_output(str(name or ""))
        if upload_id is None:
            return {"ok": False, "error": f"{name}: not an image in outputs/ (deleted?)"}
        return {"ok": True, "id": upload_id}

    def job(self, job_id: str) -> dict:
        from services import jobs

        return {"ok": True, **jobs.view(job_id or "")}

    @bff_stream()
    async def follow(self, job_id: str):
        import asyncio
        import json
        import time

        from services import jobs

        budget = float(os.environ.get("IGUANA_STREAM_BUDGET", "240"))
        heartbeat = 5.0
        t0 = last_sent = time.monotonic()
        last = None
        while True:
            state = jobs.view(job_id or "")
            key = json.dumps(state, sort_keys=True, default=str)
            now = time.monotonic()
            if key != last or now - last_sent >= heartbeat:
                yield {"type": "state", **state}
                last, last_sent = key, now
            if state.get("status") in ("done", "error", "not_found"):
                return
            if now - t0 >= budget:
                yield {"type": "continue"}
                return
            await asyncio.sleep(0.5)
