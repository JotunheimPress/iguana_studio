"""The output area: job card, live progress, results, errors.

Progress arrives over `Studio.follow()` (a @bff_stream), not 2 s polling. The stream ends
itself before pytincture's 300 s cap with `{"type": "continue"}` and is simply called again
— so a 30-minute video job, and a page reload mid-job, both just reconnect by job id. The
running job's id sits in sessionStorage for that.

The card's text and bar are rewritten in place: replacing the node restarts the CSS spinner,
which reads as the job having started over (same rule as the classic page).
"""
from __future__ import annotations

import js

from bff.studio import Studio
from ui.common import by_id, esc
from ui.gallery import menu_button

RUNNING_KEY = "iguana.job"
VIDEO = (".mp4", ".gif", ".webm")


def fmt_eta(secs) -> str:
    if secs is None or secs < 0:
        return ""
    if secs < 60:
        return f"~{secs}s left"
    return f"~{secs // 60}m {secs % 60:02d}s left"


def status_text(d: dict) -> str:
    p = d.get("progress") or {}
    phase = d.get("phase") or "working"
    if not p.get("max"):
        return phase[:1].upper() + phase[1:] + "…"
    pct = round(p["value"] / p["max"] * 100)
    eta = fmt_eta(d.get("eta"))
    return f"{phase} · step {p['value']}/{p['max']} · {pct}%" + (f" · {eta}" if eta else "")


def output_html() -> str:
    return ('<div class="output-area" id="output-area">'
            '<div class="output-placeholder" id="output-placeholder"><div class="big">🎨</div>'
            '<div>Write a prompt and hit Generate</div></div></div>')


class JobView:
    def __init__(self, on_finished) -> None:
        self.on_finished = on_finished          # called with (ok: bool) when a job ends

    # --- card -------------------------------------------------------------------------
    def status(self, msg: str) -> None:
        self.clear()
        by_id("output-placeholder").classList.add("hidden")
        div = js.document.createElement("div")
        div.className, div.id = "job-status", "job-status-el"
        div.innerHTML = (f'<div class="spinner"></div><span id="job-status-text">{esc(msg)}</span>'
                         '<div class="job-bar" id="job-bar" hidden><span></span></div>')
        by_id("output-area").prepend(div)

    def update(self, d: dict) -> None:
        el = by_id("job-status-text")
        if not el:
            return self.status(status_text(d))
        el.textContent = status_text(d)
        bar, p = by_id("job-bar"), d.get("progress") or {}
        if p.get("max"):
            bar.hidden = False
            bar.firstChild.style.width = f"{p['value'] / p['max'] * 100:.1f}%"
        else:
            bar.hidden = True

    def clear(self) -> None:
        el = by_id("job-status-el")
        if el:
            el.remove()

    def error(self, msg: str) -> None:
        self.clear()
        by_id("output-placeholder").classList.add("hidden")
        div = js.document.createElement("div")
        div.className = "error-card"
        div.textContent = "⚠ " + msg
        by_id("output-area").prepend(div)

    def outputs(self, files: list) -> None:
        by_id("output-placeholder").classList.add("hidden")
        area = by_id("output-area")
        for name in files:
            url = "/outputs/" + str(js.encodeURIComponent(name))
            card = js.document.createElement("div")
            card.className = "output-card"
            card.setAttribute("data-file", name)
            if name.lower().endswith(VIDEO):
                card.innerHTML = (f'<video src="{esc(url)}" autoplay loop muted playsinline '
                                  'controls></video>' + menu_button(name))
            else:
                # A click opens the gallery viewer (Studio wires it on #output-area).
                card.innerHTML = (f'<img class="output-img" src="{esc(url)}" alt="{esc(name)}" '
                                  'loading="lazy">' + menu_button(name))
            area.prepend(card)

    # --- following a job --------------------------------------------------------------
    async def follow(self, job_id: str) -> None:
        js.sessionStorage.setItem(RUNNING_KEY, job_id)
        last = {}
        try:
            while True:
                again = False
                async for ev in Studio().follow(job_id):
                    if ev.get("type") == "continue":
                        again = True
                        break
                    last = ev
                    if ev.get("status") in ("pending", "running"):
                        self.update(ev)
                if not again:
                    break
        finally:
            js.sessionStorage.removeItem(RUNNING_KEY)
        status = last.get("status")
        if status == "done":
            self.clear()
            self.outputs(last.get("files") or [])
            self.on_finished(True)
        elif status == "not_found":
            # The server restarted (jobs are in memory) — the work is gone with it.
            self.error("That job is no longer known to the server (it restarted).")
            self.on_finished(False)
        else:
            self.error(last.get("message") or "Unknown error")
            self.on_finished(False)

    def running_job(self) -> str:
        return str(js.sessionStorage.getItem(RUNNING_KEY) or "")
