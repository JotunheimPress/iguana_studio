"""Iguana Studio — the pytincture page (served at /iguana/; `/` redirects here).

Phases 1–3 (PYTINCTURE_PLAN.md): the shell — top bar with the ComfyUI status, the prompt
rail (ui/sidebar.py, LoRAs in ui/loras.py), the mode tabs — and all five modes end to end:
their control bars (ui/panels.py), the job card with streamed progress, and results
(ui/jobs.py). The gallery arrives in Phase 4.
"""
from __future__ import annotations

import js
from pyodide.ffi import to_js

from wapyt import CellConfig, LayoutConfig, MainWindow, message

from bff.studio import Studio
from ui.common import by_id, load_state, proxy, save_state, spawn
from ui.gallery import GalleryView, ItemMenu, gallery_html
from ui.jobs import JobView, output_html
from ui.loras import LORA_MODES, LoraStack
from ui.panels import Panels, panels_html
from ui.prompt import active_prompt
from ui.sidebar import Sidebar, sidebar_html

APP_ENTRYPOINT = "Iguana"

MODES = [("generate", "Generate"), ("person", "Person"), ("refine", "Refine"),
         ("edit", "Edit"), ("animate", "Animate")]
COMFY_POLL_MS = 10_000
TASK = {"generate": "text2img", "person": "photomaker", "refine": "img2img",
        "edit": "kontext", "animate": "img2vid"}
# What each mode needs before it can run (the classic page's checks, same wording intent).
MISSING_SOURCE = {
    "refine": "Pick a source image first.",
    "edit": "Pick a source image to edit first.",
    "animate": "Pick a source image to animate first.",
}
EMPTY_PROMPT = {
    "edit": 'Describe the change you want, e.g. "change the background to a snowy mountain".',
    "animate": ('Describe the motion, e.g. "she raises her right hand and touches her shoulder".\n\n'
                "The subject is already fixed by the source image — this box says what it DOES."),
}


class Iguana(MainWindow):
    layout_config = LayoutConfig(rows=[
        CellConfig(id="top", height="48px"),
        CellConfig(id="main", grow=1),
    ])

    def load_ui(self):
        link = js.document.createElement("link")
        link.rel, link.href = "stylesheet", "/istatic/iguana.css"
        js.document.head.appendChild(link)
        self.set_theme("dark")
        js.document.title = "Iguana Studio"
        state = load_state()
        self.mode = state.get("__mode") if state.get("__mode") in dict(MODES) else "generate"

        self.get_cell("top").getContainer().innerHTML = (
            '<div class="topbar"><h1>Iguana <span>Studio</span></h1>'
            '<div class="flex-gap"><div class="status-dot" id="status-dot"></div>'
            '<span class="status-label" id="status-label">Connecting…</span></div>'
            '<div class="topbar-right"><button class="btn-generate" id="top-gen-btn">Generate'
            '</button></div></div>')
        tabs = "".join(f'<div class="mode-tab" data-mode="{m}">{label}</div>' for m, label in MODES)
        self.get_cell("main").getContainer().innerHTML = (
            '<div class="layout">' + sidebar_html()
            + '<div class="workspace" id="workspace">'
            f'<div class="mode-tabs" id="mode-tabs">{tabs}</div>'
            + panels_html() + output_html() + gallery_html()
            + '</div></div>')

        self.comfy_up = False
        self.busy = False
        self.sidebar = Sidebar(lambda: self.mode)
        self.sidebar.mount()
        self.loras = LoraStack()
        self.loras.mount()
        self.panels = Panels(on_prompt_change=lambda: self.sidebar.update(save=False))
        self.panels.mount()
        self.jobs = JobView(self._job_finished)
        self.menu = ItemMenu(on_send=self.send_to, on_delete=self._delete)
        self.menu.bind(by_id("output-area"))
        self.gallery = GalleryView()
        self.gallery.mount(self.menu)
        by_id("output-area").addEventListener("click", proxy(self._on_result_click))
        by_id("mode-tabs").addEventListener("click", proxy(self._on_tab))
        by_id("top-gen-btn").addEventListener("click", proxy(lambda e: spawn(self.generate(), "generate")))
        self._show_mode()
        self.check_comfy()
        js.setInterval(proxy(lambda: self.check_comfy()), COMFY_POLL_MS)
        spawn(self._boot(), "boot")

    async def _boot(self):
        await self.panels.load_checkpoints()
        await self.loras.load()
        await self.gallery.load()                # the header's count
        job = self.jobs.running_job()
        if job:                                  # a reload mid-job: pick it back up
            self._set_busy(True)
            self.jobs.status("Reconnecting…")
            await self.jobs.follow(job)

    # --- modes --------------------------------------------------------------------
    def _on_tab(self, ev):
        tab = ev.target.closest(".mode-tab")
        if tab:
            self.switch_mode(str(tab.getAttribute("data-mode")))

    def switch_mode(self, mode: str):
        self.mode = mode
        save_state({"__mode": self.mode})
        self._show_mode()
        self.sidebar.update(save=False)

    # --- gallery actions -----------------------------------------------------------------
    def send_to(self, mode: str, name: str):
        """Gallery/result "⋯" → Refine/Edit/Animate with that image as the source."""
        self.gallery.close()
        self.panels.set_from_output(mode, name)
        self.switch_mode(mode)
        by_id("ctrl-" + mode).scrollIntoView()

    def _on_result_click(self, ev):
        """A result card's image → the gallery viewer (videos keep their own controls)."""
        img = ev.target.closest(".output-img")
        card = img.closest(".output-card") if img else None
        if card and not ev.target.closest(".item-menu-btn"):
            spawn(self.gallery.view(str(card.getAttribute("data-file"))), "view result")

    def _delete(self, name: str):
        spawn(self.gallery.delete(name, self._after_delete), "delete output")

    def _after_delete(self):
        # Nothing left in the results column — bring the placeholder back.
        if not by_id("output-area").querySelector(".output-card, .error-card, .job-status"):
            by_id("output-placeholder").classList.remove("hidden")

    def _show_mode(self):
        for tab in js.document.querySelectorAll(".mode-tab"):
            tab.classList.toggle("active", tab.getAttribute("data-mode") == self.mode)
        self.panels.show(self.mode)
        by_id("lora-section").classList.toggle("hidden", self.mode not in LORA_MODES)
        self._sync_button()

    def _sync_button(self):
        btn = by_id("top-gen-btn")
        btn.disabled = self.busy
        btn.textContent = "Generating…" if self.busy else "Generate"

    def _set_busy(self, busy: bool):
        self.busy = busy
        self._sync_button()

    def _job_finished(self, ok: bool):
        self._set_busy(False)
        if ok:
            spawn(self.gallery.load(), "gallery refresh")

    # --- generate ---------------------------------------------------------------------
    async def generate(self):
        if self.busy:
            return
        self.gallery.close()                     # it covers the output area
        mode = self.mode
        if not self.comfy_up:
            await message.alert("ComfyUI is not running — start the backends first.",
                                title="Generate")
            return
        title = dict(MODES)[mode]
        files = self.panels.files_for(mode)
        if mode in MISSING_SOURCE and not files:
            await message.alert(MISSING_SOURCE[mode], title=title)
            return
        if mode == "person" and not files:
            await message.alert("Add at least one reference photo.", title=title)
            return
        prompt = active_prompt(self.sidebar.fields(), mode)
        if not prompt or (mode == "person" and prompt.strip() == "img"):
            await message.alert(EMPTY_PROMPT.get(mode, "Write a prompt first."), title=title)
            return
        self._set_busy(True)
        self.jobs.status("Uploading…" if files else "Queuing…")
        try:
            # One request per file: pytincture caps a request body (48 MiB here), and a
            # PhotoMaker set of several photos would add up past it in one.
            ids = [await self._upload(f) for f in files]
            fields = {**self.panels.fields(mode), "prompt": prompt}
            if mode in LORA_MODES:
                fields["loras"] = self.loras.active()
            r = await Studio().generate_async(TASK[mode], fields, ids)
        except Exception as exc:  # noqa: BLE001 - upload/network failure → error card
            r = {"ok": False, "error": str(exc)}
        if not r.get("ok"):
            self.jobs.error(r.get("error") or "Could not start the job.")
            self._set_busy(False)
            return
        await self.jobs.follow(r["job_id"])

    async def _upload(self, file) -> str:
        if isinstance(file, dict) and file.get("output"):        # picked from the gallery
            r = await Studio().from_output_async(file["output"])
            if not r.get("ok"):
                raise RuntimeError(r.get("error") or "that gallery image is gone")
            return r["id"]
        fd = js.FormData.new()
        fd.append("files", file)
        resp = await js.fetch("/upload", to_js({"method": "POST", "body": fd},
                                               dict_converter=js.Object.fromEntries))
        data = (await resp.json()).to_py()
        if not resp.ok:
            raise RuntimeError(data.get("detail") if isinstance(data, dict) else f"upload failed ({resp.status})")
        return data["ids"][0]

    # --- ComfyUI status -----------------------------------------------------------
    def check_comfy(self):
        spawn(self._check_comfy(), "comfy status")

    async def _check_comfy(self):
        r = await Studio().comfy_status_async()
        up = bool(isinstance(r, dict) and r.get("running"))
        self.comfy_up = up
        by_id("status-dot").classList.toggle("online", up)
        by_id("status-label").textContent = "ComfyUI connected" if up else "ComfyUI offline"
