"""ComfyUI API client — queue workflows, poll for results, download outputs."""

import json
import os
import time
import uuid
import requests
from pathlib import Path

COMFY_HOST = os.environ.get("COMFY_HOST", "localhost")
COMFY_PORT = os.environ.get("COMFY_PORT", "8188")
COMFY_URL = f"http://{COMFY_HOST}:{COMFY_PORT}"


def is_running() -> bool:
    try:
        requests.get(f"{COMFY_URL}/system_stats", timeout=3)
        return True
    except requests.exceptions.ConnectionError:
        return False


def upload_image(image_path: str | Path) -> str:
    """Upload a local image to ComfyUI's input folder. Returns the server filename."""
    with open(image_path, "rb") as f:
        resp = requests.post(f"{COMFY_URL}/upload/image", files={"image": f})
    resp.raise_for_status()
    return resp.json()["name"]


def queue_prompt(workflow: dict, client_id: str | None = None) -> str:
    """Submit a workflow and return the prompt_id.

    `client_id` matters for progress: ComfyUI addresses its progress messages to the
    client that submitted the job, so the websocket has to be opened with the *same* id
    that is sent here. Left unset it is random, which is fine for fire-and-forget.
    """
    client_id = client_id or str(uuid.uuid4())
    resp = requests.post(
        f"{COMFY_URL}/prompt",
        json={"prompt": workflow, "client_id": client_id},
    )
    if not resp.ok:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text
        raise RuntimeError(f"ComfyUI rejected the workflow (HTTP {resp.status_code}): {detail}")
    return resp.json()["prompt_id"]


def wait_for_completion(prompt_id: str, timeout: int = 600, poll_interval: float = 1.5) -> dict:
    """Poll /history until the job is done. Raises TimeoutError if it takes too long."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(f"{COMFY_URL}/history/{prompt_id}")
        resp.raise_for_status()
        history = resp.json()
        if prompt_id in history:
            return history[prompt_id]
        time.sleep(poll_interval)
    raise TimeoutError(f"Job {prompt_id} did not finish within {timeout}s")


def _collect_output_items(result: dict) -> list[dict]:
    """Every downloadable file a finished job produced, across every output key.

    Two traps here, both found the hard way against SaveVideo:

    * **Not every entry is a file.** SaveVideo reports its mp4 under `images` and sets
      `"animated": [true]` alongside — a list of *booleans*. Extending blindly put `True`
      in this list and `download_outputs` then died on `item["filename"]`, i.e. after a
      multi-minute render had already succeeded. Only real file dicts are taken.
    * **One file can appear under two keys**, so the same bytes would be fetched twice and
      the UI would render two cards for one result. Identity is (filename, subfolder,
      type) — the same triple `/view` is addressed by.
    """
    items, seen = [], set()
    for node_output in result.get("outputs", {}).values():
        for key in ("images", "gifs", "videos", "animated"):
            for item in node_output.get(key, []):
                if not isinstance(item, dict) or "filename" not in item:
                    continue
                ident = (item["filename"], item.get("subfolder", ""), item.get("type", "output"))
                if ident in seen:
                    continue
                seen.add(ident)
                items.append(item)
    return items


def download_outputs(result: dict, save_dir: str | Path = "outputs") -> list[Path]:
    """Download every output file from a completed job result."""
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    for item in _collect_output_items(result):
        params = {
            "filename": item["filename"],
            "subfolder": item.get("subfolder", ""),
            "type": item.get("type", "output"),
        }
        resp = requests.get(f"{COMFY_URL}/view", params=params)
        resp.raise_for_status()
        out_path = save_dir / item["filename"]
        out_path.write_bytes(resp.content)
        paths.append(out_path)

    return paths


def _watch_progress(workflow: dict, timeout: int, on_progress) -> str:
    """Queue a workflow over a websocket subscription and report progress until it ends.

    ComfyUI exposes step-level progress *only* over the websocket — `/api/jobs/{id}`
    carries a status and a duration but no step counter, and there is no REST progress
    route. So this is the one way to know a 3-minute render is 40% done rather than hung.

    The socket is opened **before** the job is queued. Connecting afterwards races the
    first `progress` messages, and on a short job that means the bar never moves at all.

    `on_progress(value, max, node)` is called with the sampler step counter; `node` also
    arrives on its own at each node transition (value/max None) so the caller can name the
    phase. Sampling is the bulk of a video job but not all of it: the model load happens
    before the first step and the VAE decode plus mp4 mux after the last, which is why the
    phase is reported separately instead of pretending the step bar covers the whole run.
    """
    import websocket                                   # websocket-client, sync by design

    cid = str(uuid.uuid4())
    ws = websocket.WebSocket()
    # Anything that fails before the job is queued propagates: nothing is running yet, so
    # the caller is free to fall back to an ordinary queue+poll.
    ws.connect(f"ws://{COMFY_HOST}:{COMFY_PORT}/ws?clientId={cid}", timeout=10)
    try:
        prompt_id = queue_prompt(workflow, client_id=cid)
    except Exception:
        ws.close()
        raise
    print(f"  Job ID: {prompt_id}")

    def report(value, maximum, node):
        # A caller's progress callback must not be able to kill the watch — and if it
        # could, the failure would surface as a re-queued duplicate render.
        try:
            on_progress(value, maximum, node)
        except Exception:                               # noqa: BLE001 - cosmetic only
            pass

    try:
        deadline = time.time() + timeout
        ws.settimeout(5)
        while time.time() < deadline:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue                                # idle socket, not a stalled job
            if isinstance(raw, bytes):
                continue                                # preview images; not our business
            msg = json.loads(raw)
            kind, data = msg.get("type"), msg.get("data") or {}
            # Messages for other jobs share this socket; ones with no prompt_id at all
            # (e.g. queue status) are global and harmless to ignore.
            if data.get("prompt_id") not in (None, prompt_id):
                continue
            if kind == "progress":
                report(data.get("value"), data.get("max"), data.get("node"))
            elif kind == "executing":
                if data.get("node") is None and data.get("prompt_id") == prompt_id:
                    return prompt_id
                report(None, None, data.get("node"))
            elif kind in ("execution_success", "execution_error", "execution_interrupted"):
                if data.get("prompt_id") == prompt_id:
                    return prompt_id
        raise TimeoutError(f"Job {prompt_id} did not finish within {timeout}s")
    except TimeoutError:
        raise
    except Exception as e:                              # noqa: BLE001
        # The socket died, but the JOB is still running on the other side. Handing the id
        # back so the caller can poll for it is the whole point — re-queueing here would
        # silently render a multi-minute video twice.
        print(f"  (progress stream ended: {e}; polling for the result instead)")
        return prompt_id
    finally:
        try:
            ws.close()
        except Exception:                               # noqa: BLE001 - best effort
            pass


def run_workflow(
    workflow: dict,
    save_dir: str | Path = "outputs",
    timeout: int = 600,
    on_progress=None,
) -> list[Path]:
    """Queue a workflow, wait for it, download results. Returns saved file paths.

    With `on_progress` the wait happens over the websocket so progress can be reported;
    without it, or if the socket cannot be established, it falls back to polling
    `/history`. **Progress is a nicety and the render is the point**, so a websocket
    failure must never fail a job that would otherwise have succeeded.
    """
    if not is_running():
        raise ConnectionError(
            "ComfyUI is not running. Start it and try again (default port 8188)."
        )

    print("Queueing workflow...")
    prompt_id = None
    if on_progress is not None:
        try:
            prompt_id = _watch_progress(workflow, timeout, on_progress)
        except (TimeoutError, RuntimeError):
            raise
        except Exception as e:                          # noqa: BLE001 - degrade, don't fail
            print(f"  (progress unavailable: {e}; falling back to polling)")

    if prompt_id is None:
        prompt_id = queue_prompt(workflow)
        print(f"  Job ID: {prompt_id}")

    print("Waiting for completion (this may take a while)...")
    result = wait_for_completion(prompt_id, timeout=timeout)

    status = result.get("status", {})
    if status.get("status_str") == "error":
        msgs = [m for m in status.get("messages", []) if m[0] == "execution_error"]
        raise RuntimeError(f"Workflow failed: {msgs}")

    paths = download_outputs(result, save_dir)
    for p in paths:
        print(f"  Saved → {p}")
    return paths
