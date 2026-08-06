"""ComfyUI API client — queue workflows, poll for results, download outputs."""

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


def queue_prompt(workflow: dict) -> str:
    """Submit a workflow and return the prompt_id."""
    client_id = str(uuid.uuid4())
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
    items = []
    for node_output in result.get("outputs", {}).values():
        for key in ("images", "gifs", "videos", "animated"):
            items.extend(node_output.get(key, []))
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


def run_workflow(
    workflow: dict,
    save_dir: str | Path = "outputs",
    timeout: int = 600,
) -> list[Path]:
    """Queue a workflow, wait for it, download results. Returns saved file paths."""
    if not is_running():
        raise ConnectionError(
            "ComfyUI is not running. Start it and try again (default port 8188)."
        )

    print("Queueing workflow...")
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
