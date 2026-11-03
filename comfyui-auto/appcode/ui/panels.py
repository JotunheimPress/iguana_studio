"""The five modes' control bars — ports of the classic page's ctrl-* sections.

Per-checkpoint tuning is split in two, as on the classic page, so a reload never throws the
user's own numbers away:
  * `_apply_ui()` — architecture only (CFG ↔ Guidance label, negative hidden for FLUX); safe
    on every boot.
  * `_apply_config()` — also stamps the recommended w/h/steps/CFG (from the server,
    services.models); only on an explicit model change, or a first visit with nothing saved.

The checkpoint selects fill asynchronously, so their saved value is restored from the state
blob once the list arrives — and an empty select never overwrites a saved choice.

Every image preview (Refine/Edit/Animate source, Person thumbnails) is a data: URL via
FileReader: pytincture's CSP has no `blob:` in img-src, so URL.createObjectURL is blocked.

Animate sends an EMPTY negative on purpose: the server then uses workflows/video.py's
NEGATIVE_VIDEO, which was tuned by measurement not to suppress motion. The classic page sent
the Generate panel's image negative here (a box Animate doesn't even show), overriding it.
"""
from __future__ import annotations

import js

from bff.studio import Studio
from ui.common import by_id, esc, load_state, proxy, save_state

BASE_ORDER = ["FLUX.2", "Z-Image", "FLUX", "SDXL", "SD 1.5"]
NUMERIC = {
    "g": ["g-width", "g-height", "g-steps", "g-cfg"],
    "r": ["r-steps", "r-cfg"],
}
# Fields this module persists (shared with the classic page's PERSIST_IDS).
PANEL_IDS = ["g-width", "g-height", "g-steps", "g-cfg", "g-seed",
             "r-denoise", "r-steps", "r-cfg", "r-seed", "neg-prompt",
             "pm-model", "pm-width", "pm-height", "pm-steps", "pm-cfg",
             "k-instruction", "k-guidance", "k-steps", "k-seed",
             "v-motion", "v-length", "v-fps", "v-size", "v-steps", "v-cfg", "v-shift", "v-seed"]
SOURCE_MODES = ("refine", "edit", "animate")
MODE_IDS = ("generate", "person", "refine", "edit", "animate")
ASYNC_IDS = ["g-checkpoint", "r-checkpoint"]


def _num(id_, value, mn, mx, step, width):
    return (f'<input type="number" id="{id_}" value="{value}" min="{mn}" max="{mx}" step="{step}"'
            f' style="width:{width}px">')


def panels_html() -> str:
    return (
        '<div class="controls-bar">'
        '<div id="ctrl-generate" class="ctrl-section">'
        '<div class="ctrl-group"><label>Model</label><select id="g-checkpoint"><option value="">Loading…</option></select></div>'
        f'<div class="ctrl-group"><label>Width</label>{_num("g-width", 1024, 256, 2048, 64, 72)}</div>'
        f'<div class="ctrl-group"><label>Height</label>{_num("g-height", 1024, 256, 2048, 64, 72)}</div>'
        f'<div class="ctrl-group"><label>Steps</label>{_num("g-steps", 25, 1, 150, 1, 58)}</div>'
        f'<div class="ctrl-group"><label id="g-cfg-label">CFG</label>{_num("g-cfg", 7, 0.1, 100, 0.5, 58)}</div>'
        f'<div class="ctrl-group"><label>Seed (-1=random)</label>{_num("g-seed", -1, -1, 4294967295, 1, 90)}</div>'
        '<div class="ctrl-group neg-group" id="neg-group"><span class="neg-toggle" id="neg-toggle">▾ Negative prompt</span>'
        '<div id="neg-wrap"><textarea id="neg-prompt" rows="2" placeholder="negative prompt…"></textarea></div></div>'
        '</div>'
        '<div id="ctrl-refine" class="ctrl-section hidden">'
        + _source("refine") +
        '<div class="ctrl-group"><label>Model</label><select id="r-checkpoint"><option value="">Loading…</option></select></div>'
        '<div class="ctrl-group"><label>Denoise <span id="denoise-val">0.65</span></label>'
        '<input type="range" id="r-denoise" min="0.1" max="1.0" step="0.05" value="0.65" class="denoise"></div>'
        f'<div class="ctrl-group"><label>Steps</label>{_num("r-steps", 25, 1, 150, 1, 58)}</div>'
        f'<div class="ctrl-group"><label id="r-cfg-label">CFG</label>{_num("r-cfg", 7, 0.1, 100, 0.5, 58)}</div>'
        f'<div class="ctrl-group"><label>Seed (-1=random)</label>{_num("r-seed", -1, -1, 4294967295, 1, 90)}</div>'
        '</div>'
        # Person (PhotoMaker)
        '<div id="ctrl-person" class="ctrl-section hidden">'
        '<div class="ctrl-group"><label>PhotoMaker</label><select id="pm-model">'
        '<option value="photomaker-v2.bin" selected>V2 (recommended)</option>'
        '<option value="photomaker-v1.bin">V1</option></select></div>'
        f'<div class="ctrl-group"><label>Width</label>{_num("pm-width", 1024, 512, 2048, 64, 72)}</div>'
        f'<div class="ctrl-group"><label>Height</label>{_num("pm-height", 1024, 512, 2048, 64, 72)}</div>'
        f'<div class="ctrl-group"><label>Steps</label>{_num("pm-steps", 25, 1, 150, 1, 58)}</div>'
        f'<div class="ctrl-group"><label>CFG</label>{_num("pm-cfg", 7, 1, 30, 0.5, 58)}</div>'
        '<div class="ctrl-group"><label>Reference photos</label>'
        '<div class="dropzone" id="person-dropzone"><div class="icon">📷</div><p>Click or drag photos</p></div>'
        '<input type="file" id="person-upload-input" multiple accept="image/*" hidden></div>'
        '<div class="ctrl-group hidden" id="person-thumbs-col"><label>Loaded (<span id="person-count">0</span>)'
        ' — click to remove</label><div class="thumb-strip" id="person-thumbs"></div></div>'
        '<div class="ctrl-group"><label class="tip-label">Prompt tip</label><span class="tip">'
        '<code>img</code> is added before the prompt automatically in Person mode.</span></div>'
        '</div>'
        # Edit (Flux Kontext)
        '<div id="ctrl-edit" class="ctrl-section hidden">'
        + _source("edit") +
        '<div class="ctrl-group grow"><label>Instruction</label><textarea id="k-instruction" rows="2" '
        'placeholder="change the background to a snowy mountain…"></textarea></div>'
        '<div class="ctrl-group"><label>Guidance <span id="k-guidance-val">2.5</span></label>'
        '<input type="range" id="k-guidance" min="1.0" max="5.0" step="0.1" value="2.5" class="slider"></div>'
        f'<div class="ctrl-group"><label>Steps</label>{_num("k-steps", 20, 1, 60, 1, 58)}</div>'
        f'<div class="ctrl-group"><label>Seed (-1=random)</label>{_num("k-seed", -1, -1, 4294967295, 1, 90)}</div>'
        '</div>'
        # Animate (WAN 2.2 TI2V 5B)
        '<div id="ctrl-animate" class="ctrl-section hidden">'
        + _source("animate") +
        '<div class="ctrl-group grow"><label>Motion</label><textarea id="v-motion" rows="2" '
        'placeholder="she raises her right hand and touches her shoulder…"></textarea></div>'
        '<div class="ctrl-group"><label>Length <span id="v-length-val">81f · 3.4s</span></label>'
        f'{_num("v-length", 81, 5, 121, 4, 64)}</div>'
        f'<div class="ctrl-group"><label>FPS</label>{_num("v-fps", 24, 1, 60, 1, 58)}</div>'
        '<div class="ctrl-group"><label>Size</label><select id="v-size">'
        '<option value="1280x704" selected>1280×704 (native)</option><option value="960x544">960×544</option>'
        '<option value="704x1280">704×1280 (portrait)</option><option value="640x640">640×640</option></select></div>'
        f'<div class="ctrl-group"><label>Steps</label>{_num("v-steps", 30, 1, 80, 1, 58)}</div>'
        f'<div class="ctrl-group"><label>CFG</label>{_num("v-cfg", 5, 0.1, 20, 0.5, 58)}</div>'
        f'<div class="ctrl-group"><label>Shift</label>{_num("v-shift", 8, 1, 20, 0.5, 58)}</div>'
        f'<div class="ctrl-group"><label>Seed (-1=random)</label>{_num("v-seed", -1, -1, 4294967295, 1, 90)}</div>'
        '</div>'
        '</div>')


def _source(prefix: str) -> str:
    return ('<div class="ctrl-group"><label>Source image</label><div class="src-pick">'
            f'<div class="refine-placeholder" id="{prefix}-placeholder" title="Click to upload">+</div>'
            f'<img id="{prefix}-thumb" class="refine-thumb hidden" alt="source" title="Click to change">'
            f'<input type="file" id="{prefix}-upload-input" accept="image/*" hidden>'
            f'<span id="{prefix}-name" class="src-name"></span></div></div>')


def snap_length(raw, fps) -> tuple[int, str]:
    """Mirror of workflows/video.clamp_length() for the label: 4n+1 within 5–121, rounded down."""
    try:
        n = int(float(raw))
    except (TypeError, ValueError):
        n = 81
    try:
        f = max(int(float(fps)), 1)
    except (TypeError, ValueError):
        f = 24
    n = ((max(5, min(n, 121)) - 1) // 4) * 4 + 1
    return n, f"{n}f · {n / f:.1f}s"


def _read_data_url(file, on_done) -> None:
    reader = js.FileReader.new()
    reader.onload = proxy(lambda _e: on_done(str(reader.result)))
    reader.readAsDataURL(file)


class Panels:
    def __init__(self, on_prompt_change=None) -> None:
        self.ckpts: dict[str, dict] = {}       # name -> {base, config}
        self.sources: dict = {m: None for m in SOURCE_MODES}   # mode -> picked JS File
        self.person_files: list = []           # JS Files, in the order added
        self.default_negative = ""
        self.on_prompt_change = on_prompt_change or (lambda: None)

    @property
    def refine_file(self):
        return self.sources["refine"]

    def mount(self) -> None:
        state = load_state()
        for fid in PANEL_IDS:
            if fid in state and by_id(fid):
                by_id(fid).value = str(state[fid])
        by_id("denoise-val").textContent = f"{float(by_id('r-denoise').value):.2f}"
        by_id("k-guidance-val").textContent = f"{float(by_id('k-guidance').value):.1f}"
        self._length_label()
        bar = by_id("ctrl-generate").parentElement
        bar.addEventListener("input", proxy(self._on_input))
        bar.addEventListener("change", proxy(self._on_change))
        by_id("neg-toggle").addEventListener("click", proxy(
            lambda e: by_id("neg-wrap").classList.toggle("open")))
        for mode in SOURCE_MODES:
            self._wire_source(mode)
        dz = by_id("person-dropzone")
        dz.addEventListener("click", proxy(lambda e: by_id("person-upload-input").click()))
        dz.addEventListener("dragover", proxy(self._on_dragover))
        dz.addEventListener("dragleave", proxy(lambda e: dz.classList.remove("drag")))
        dz.addEventListener("drop", proxy(self._on_drop))
        by_id("person-upload-input").addEventListener("change", proxy(
            lambda e: self._add_person(by_id("person-upload-input").files)))
        by_id("person-thumbs").addEventListener("click", proxy(self._on_thumb))

    def show(self, mode: str) -> None:
        for m in MODE_IDS:
            by_id(f"ctrl-{m}").classList.toggle("hidden", mode != m)

    # --- persistence ---------------------------------------------------------------------
    def _on_input(self, ev) -> None:
        tid = str(ev.target.id)
        if tid == "r-denoise":
            by_id("denoise-val").textContent = f"{float(ev.target.value):.2f}"
        elif tid == "k-guidance":
            by_id("k-guidance-val").textContent = f"{float(ev.target.value):.1f}"
        elif tid in ("v-length", "v-fps"):
            self._length_label()
        if tid in PANEL_IDS:
            save_state({tid: str(ev.target.value)})
        if tid in ("k-instruction", "v-motion"):
            self.on_prompt_change()              # these ARE the prompt in Edit/Animate

    def _length_label(self) -> None:
        _, text = snap_length(by_id("v-length").value, by_id("v-fps").value)
        by_id("v-length-val").textContent = text

    def _on_change(self, ev) -> None:
        tid = str(ev.target.id)
        if tid in ASYNC_IDS and str(ev.target.value):
            save_state({tid: str(ev.target.value)})
            self._apply_config(str(ev.target.value), tid[0])      # explicit change
        elif tid in PANEL_IDS:
            save_state({tid: str(ev.target.value)})

    # --- checkpoints -------------------------------------------------------------------
    async def load_checkpoints(self) -> None:
        r = await Studio().checkpoints_async()
        cps = (r or {}).get("checkpoints") or []
        self.ckpts = {c["name"]: c for c in cps}
        self.default_negative = str((r or {}).get("negative") or "")
        neg = by_id("neg-prompt")
        state = load_state()
        if "neg-prompt" not in state and not str(neg.value) and self.default_negative:
            neg.value = self.default_negative
        seen = {c["base"] for c in cps}
        order = [b for b in BASE_ORDER if b in seen] + sorted(seen - set(BASE_ORDER))
        html = "".join(
            f'<optgroup label="{esc(base)}">' + "".join(
                f'<option value="{esc(c["name"])}">{esc(_label(c["name"]))}</option>'
                for c in cps if c["base"] == base) + "</optgroup>"
            for base in order) or '<option value="">ComfyUI offline</option>'
        for sid in ASYNC_IDS:
            sel = by_id(sid)
            sel.innerHTML = html
            if state.get(sid) in self.ckpts:
                sel.value = state[sid]
        for sid, prefix in (("g-checkpoint", "g"), ("r-checkpoint", "r")):
            ckpt = str(by_id(sid).value)
            if all(str(state.get(f, "")) != "" for f in NUMERIC[prefix]):
                self._apply_ui(ckpt, prefix)
            else:
                self._apply_config(ckpt, prefix)

    def base_of(self, ckpt: str) -> str:
        c = self.ckpts.get(ckpt)
        if c:
            return c["base"]
        low = ckpt.lower()
        if "flux2" in low or "flux-2" in low or "flux.2" in low or "flux_2" in low:
            return "FLUX.2"
        if "z_image" in low or "zimage" in low or "z-image" in low:
            return "Z-Image"
        return "FLUX" if "flux" in low else "SDXL" if "xl" in low else "SD 1.5"

    def _apply_ui(self, ckpt: str, prefix: str) -> None:
        flux = self.base_of(ckpt) == "FLUX"
        conf = (self.ckpts.get(ckpt) or {}).get("config") or {}
        by_id(f"{prefix}-cfg-label").textContent = (
            "Guidance" if flux else conf.get("cfg_label") or "CFG")
        if prefix == "g":
            # FLUX never takes a negative; others say so in their config (Z-Image Turbo,
            # FLUX.2 Dev and Klein distilled).
            by_id("neg-group").classList.toggle("hidden", flux or conf.get("neg") is False)

    def _apply_config(self, ckpt: str, prefix: str) -> None:
        self._apply_ui(ckpt, prefix)
        conf = (self.ckpts.get(ckpt) or {}).get("config")
        if not conf:
            return
        values = ({"g-width": conf["w"], "g-height": conf["h"], "g-steps": conf["steps"],
                   "g-cfg": conf["cfg"]} if prefix == "g"
                  else {"r-steps": conf["steps"], "r-cfg": conf["cfg"]})
        for fid, v in values.items():
            by_id(fid).value = str(v)
        save_state({k: str(v) for k, v in values.items()})

    # --- single-image sources (Refine / Edit / Animate) -----------------------------------
    def _wire_source(self, mode: str) -> None:
        pick = proxy(lambda e: by_id(f"{mode}-upload-input").click())
        by_id(f"{mode}-placeholder").addEventListener("click", pick)
        by_id(f"{mode}-thumb").addEventListener("click", pick)
        by_id(f"{mode}-upload-input").addEventListener("change", proxy(lambda e: self._on_source(mode)))

    def set_from_output(self, mode: str, name: str) -> None:
        """Gallery → Refine/Edit/Animate: the source is an image already in outputs/. Kept
        as a marker; at generate time the server copies it into temp/ (Studio.from_output)."""
        self.sources[mode] = {"output": name}
        img = by_id(f"{mode}-thumb")
        img.src = "/outputs/" + str(js.encodeURIComponent(name))   # same-origin: CSP-fine
        img.classList.remove("hidden")
        by_id(f"{mode}-placeholder").classList.add("hidden")
        by_id(f"{mode}-name").textContent = name
        by_id(f"{mode}-upload-input").value = ""

    def _on_source(self, mode: str) -> None:
        files = by_id(f"{mode}-upload-input").files
        if not files.length:
            return
        f = files.item(0)
        self.sources[mode] = f
        by_id(f"{mode}-name").textContent = str(f.name)

        def show(url):
            img = by_id(f"{mode}-thumb")
            img.src = url
            img.classList.remove("hidden")
            by_id(f"{mode}-placeholder").classList.add("hidden")

        _read_data_url(f, show)

    # --- Person reference photos -----------------------------------------------------------
    def _on_dragover(self, ev) -> None:
        ev.preventDefault()
        by_id("person-dropzone").classList.add("drag")

    def _on_drop(self, ev) -> None:
        ev.preventDefault()
        by_id("person-dropzone").classList.remove("drag")
        self._add_person(ev.dataTransfer.files)

    def _add_person(self, files) -> None:
        for i in range(files.length):
            f = files.item(i)
            if str(f.type).startswith("image/"):
                self.person_files.append({"file": f, "url": ""})
        by_id("person-upload-input").value = ""          # same file can be added again
        self._render_person()
        for entry in self.person_files:
            if not entry["url"]:
                _read_data_url(entry["file"], lambda url, e=entry: self._thumb_ready(e, url))

    def _thumb_ready(self, entry, url) -> None:
        entry["url"] = url
        self._render_person()

    def _render_person(self) -> None:
        by_id("person-thumbs").innerHTML = "".join(
            f'<img data-i="{i}" src="{esc(e["url"])}" title="Click to remove" alt="">'
            if e["url"] else f'<span class="thumb-wait" data-i="{i}"></span>'
            for i, e in enumerate(self.person_files))
        by_id("person-count").textContent = str(len(self.person_files))
        by_id("person-thumbs-col").classList.toggle("hidden", not self.person_files)

    def _on_thumb(self, ev) -> None:
        i = ev.target.getAttribute("data-i")
        if i is not None and str(i).isdigit():
            self.person_files.pop(int(i))
            self._render_person()

    def files_for(self, mode: str) -> list:
        """The JS Files a mode uploads, in order."""
        if mode == "person":
            return [e["file"] for e in self.person_files]
        f = self.sources.get(mode)
        return [f] if f else []

    # --- what a mode sends ------------------------------------------------------------
    def fields(self, mode: str) -> dict:
        def val(i):
            return str(by_id(i).value or "")
        neg = val("neg-prompt").strip()
        if mode == "generate":
            return {"negative": neg, "checkpoint": val("g-checkpoint"), "width": val("g-width"),
                    "height": val("g-height"), "steps": val("g-steps"), "cfg": val("g-cfg"),
                    "seed": val("g-seed")}
        if mode == "refine":
            return {"negative": neg, "checkpoint": val("r-checkpoint"), "denoise": val("r-denoise"),
                    "steps": val("r-steps"), "cfg": val("r-cfg"), "seed": val("r-seed")}
        if mode == "person":
            return {"negative": neg, "pm_model": val("pm-model"), "pm_width": val("pm-width"),
                    "pm_height": val("pm-height"), "steps": val("pm-steps"), "cfg": val("pm-cfg")}
        if mode == "edit":
            # Guidance rides on `cfg` (the server's convention); sampler CFG is pinned to 1.
            return {"cfg": val("k-guidance"), "steps": val("k-steps"), "seed": val("k-seed")}
        if mode == "animate":
            w, _, h = val("v-size").partition("x")
            length, _ = snap_length(val("v-length"), val("v-fps"))
            return {"negative": "", "width": w, "height": h, "length": length, "fps": val("v-fps"),
                    "steps": val("v-steps"), "cfg": val("v-cfg"), "shift": val("v-shift"),
                    "seed": val("v-seed")}
        return {}


def _label(filename: str) -> str:
    import re

    return re.sub(r"[_-]+", " ", re.sub(r"\.(safetensors|ckpt|pt|bin|gguf)$", "", filename, flags=re.I))
