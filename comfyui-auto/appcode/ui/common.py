"""Browser-side helpers shared by every part of the page. Runs in Pyodide only.

Import *names* from here (``from ui.common import spawn``), never the module: pytincture's
packager follows only that form. Never name a ``js.window`` attribute with a leading
double underscore inside a class — Python mangles it (``__x`` → ``_Class__x``).
"""
from __future__ import annotations

import asyncio
import html
import json
import traceback

import js
from pyodide.ffi import create_proxy

from wapyt import message

_KEEP: list = []


def spawn(coro, label: str):
    """Run a coroutine detached, but never silently — ensure_future swallows errors."""

    async def _guarded():
        try:
            await coro
        except Exception:  # noqa: BLE001 - last line of defence
            js.console.error(f"[iguana] {label} failed:\n{traceback.format_exc()}")

    return asyncio.ensure_future(_guarded())


def proxy(fn):
    """A JS-callable proxy kept alive for the page's lifetime (listeners, timers)."""
    p = create_proxy(fn)
    _KEEP.append(p)
    return p


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def by_id(element_id: str):
    """``getElementById``; a miss is ``JsNull`` (falsy, but not ``None``)."""
    return js.document.getElementById(element_id)


def toast(text: str, kind: str = "info", timeout_ms: int = 4000) -> None:
    message.toast(text, kind=kind, timeout_ms=timeout_ms)


def failed(result, what: str) -> bool:
    """True (and a toast) when a BFF result is an error: ``if failed(r, "x"): return``."""
    if isinstance(result, dict) and result.get("ok"):
        return False
    error = result.get("error") if isinstance(result, dict) else None
    toast(f"Could not {what}: {error}" if error else f"Could not {what}.", kind="error",
          timeout_ms=7000)
    return True


# ── the classic page's browser state ─────────────────────────────────────────
# The classic page's localStorage blob, kept so nobody lost their fields at the switch-over.
# Writes MERGE, so keys written by another part of the page are never dropped.
STATE_KEY = "studio_v1"


def load_state() -> dict:
    try:
        data = json.loads(js.localStorage.getItem(STATE_KEY) or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 - private mode, corrupt blob
        return {}


def save_state(patch: dict) -> None:
    data = load_state()
    data.update(patch)
    try:
        js.localStorage.setItem(STATE_KEY, json.dumps(data))
    except Exception:  # noqa: BLE001 - storage full / blocked: state just won't persist
        pass
