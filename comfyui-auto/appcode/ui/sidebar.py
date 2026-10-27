"""The prompt rail: manual prompt, saved prompts, preview, and the modifier dropdowns.

Built from data (ui/modifiers.py) instead of markup. The page owns the mode; this asks it
via `get_mode()` so the preview shows what the mode will actually send.

Saved prompts behave as on the classic page: picking one loads it (asking first if the
sidebar holds a different, non-empty prompt); Save asks for a name and overwrites by name
after a confirm; ✕ deletes. They hold the sidebar plus the negative prompt — never the
model, LoRAs or sampler settings.
"""
from __future__ import annotations

import js

from wapyt import message

from bff.prompts import Prompts
from ui.common import by_id, esc, failed, load_state, proxy, save_state, spawn
from ui.loras import loras_html
from ui.modifiers import SECTIONS
from ui.prompt import PROMPT_FIELDS, SAVED_PROMPT_FIELDS, SIDEBAR_UNUSED, active_prompt


def _select_html(fid: str, groups) -> str:
    opts = []
    for group, options in groups:
        inner = "".join(f'<option value="{esc(v)}">{esc(t)}</option>' for v, t in options)
        opts.append(f'<optgroup label="{esc(group)}">{inner}</optgroup>' if group else inner)
    return f'<select id="{fid}" data-pf="1">{"".join(opts)}</select>'


def sidebar_html() -> str:
    sections = []
    for title, fields in SECTIONS:
        cells = "".join(
            f'<div class="field"><label for="{fid}">{esc(label)}</label>{_select_html(fid, groups)}</div>'
            for fid, label, groups in fields)
        sections.append(f'<div class="section-label">{esc(title)}</div><div class="field-grid">{cells}</div>')
    return (
        '<aside class="sidebar"><div class="sidebar-inner" id="sb">'
        '<div class="prompt-sticky">'
        '<div class="section-label sb-head">Prompt<button class="btn-clear" id="sb-clear">Clear</button></div>'
        '<div class="saved-row">'
        '<select id="saved-prompts" title="Load a saved prompt"><option value="">Saved prompts…</option></select>'
        '<button id="sp-save" title="Save the sidebar (text, dropdowns, negative) under a name">Save</button>'
        '<button id="sp-del" title="Delete the selected saved prompt" disabled>✕</button>'
        '</div>'
        '<textarea class="extra-prompt" id="f-extra" data-pf="1" rows="7" placeholder="Describe the '
        'subject — this is the prompt. The dropdowns below only append modifiers."></textarea>'
        '<div class="section-label" style="margin-top:10px">Preview</div>'
        '<div class="prompt-preview" id="prompt-preview">—</div>'
        '</div>'
        + loras_html()
        + "".join(sections)
        + '</div></aside>')


class Sidebar:
    def __init__(self, get_mode) -> None:
        self.get_mode = get_mode
        self.saved: list = []

    # --- wiring ------------------------------------------------------------------
    def mount(self) -> None:
        sb = by_id("sb")
        on_field = proxy(self._on_field)
        sb.addEventListener("input", on_field)
        sb.addEventListener("change", on_field)
        by_id("sb-clear").addEventListener("click", proxy(lambda e: self.clear()))
        by_id("sp-save").addEventListener("click", proxy(lambda e: spawn(self.save_prompt(), "save prompt")))
        by_id("sp-del").addEventListener("click", proxy(lambda e: spawn(self.delete_prompt(), "delete prompt")))
        by_id("saved-prompts").addEventListener("change", proxy(self._on_pick))
        self.restore()
        spawn(self.load_saved(), "saved prompts")

    def _on_field(self, ev) -> None:
        if ev.target.getAttribute("data-pf"):
            self.update()

    # --- fields + state ------------------------------------------------------------
    def fields(self) -> dict:
        """The prompt fields as they stand, plus the mode-box values the preview needs."""
        out = {fid: str(by_id(fid).value or "") for fid in PROMPT_FIELDS}
        state = load_state()
        # From its panel when the panel exists, else from the shared state (Edit/Animate
        # boxes arrive in Phase 3).
        for key in ("neg-prompt", "k-instruction", "v-motion"):
            el = by_id(key)
            out[key] = str(el.value or "") if el else str(state.get(key) or "")
        return out

    def restore(self) -> None:
        state = load_state()
        for fid in PROMPT_FIELDS:
            if fid in state:
                self._set(fid, state[fid])
        self.update(save=False)

    def _set(self, fid: str, value) -> None:
        el = by_id(fid)
        if not el:
            return
        value = str(value or "")
        el.value = value
        # A value that is no longer offered falls back to "—" rather than a stale pick.
        if el.tagName == "SELECT" and str(el.value) != value:
            el.value = ""

    def update(self, save: bool = True) -> None:
        mode = self.get_mode()
        f = self.fields()
        text = active_prompt(f, mode)
        el = by_id("prompt-preview")
        note = not text and mode in SIDEBAR_UNUSED
        el.textContent = text or SIDEBAR_UNUSED.get(mode) or "—"
        el.classList.toggle("preview-note", bool(note))
        if save:
            save_state({fid: f[fid] for fid in PROMPT_FIELDS})

    def clear(self) -> None:
        for fid in PROMPT_FIELDS:
            by_id(fid).value = ""
        self.update()

    # --- saved prompts --------------------------------------------------------------
    def _render_saved(self, select: str = "") -> None:
        sel = by_id("saved-prompts")
        head = "Saved prompts…" if self.saved else "No saved prompts yet"
        sel.innerHTML = f'<option value="">{head}</option>' + "".join(
            f'<option value="{esc(p["name"])}">{esc(p["name"])}</option>' for p in self.saved)
        sel.value = select
        by_id("sp-del").disabled = not bool(str(sel.value))

    async def load_saved(self, select: str = "") -> None:
        r = await Prompts().all_async()
        self.saved = r.get("prompts") or [] if isinstance(r, dict) else []
        self._render_saved(select)

    def _on_pick(self, _ev) -> None:
        name = str(by_id("saved-prompts").value)
        by_id("sp-del").disabled = not name
        if name:
            spawn(self.apply_saved(name), "load prompt")

    async def apply_saved(self, name: str) -> None:
        p = next((x for x in self.saved if x.get("name") == name), None)
        if not p:
            return
        saved = p.get("fields") or {}
        now = self.fields()
        dirty = any(now[f] for f in PROMPT_FIELDS) and any(
            (now.get(f) or "") != (saved.get(f) or "") for f in SAVED_PROMPT_FIELDS)
        if dirty and not await message.confirm(f'Replace the current prompt with "{name}"?',
                                               title="Load saved prompt", ok_text="Replace"):
            self._render_saved("")
            return
        for fid in PROMPT_FIELDS:
            self._set(fid, saved.get(fid, ""))
        neg = by_id("neg-prompt")
        if neg:
            neg.value = saved.get("neg-prompt", "")
        save_state({"neg-prompt": saved.get("neg-prompt", "")})
        self.update()
        by_id("sp-del").disabled = False

    async def save_prompt(self) -> None:
        f = self.fields()
        if not any(f[x] for x in PROMPT_FIELDS):
            await message.alert("There is no prompt to save yet.", title="Save prompt")
            return
        current = str(by_id("saved-prompts").value)
        first = f["f-extra"].replace("\n", ",").replace(".", ",").split(",")[0].strip()[:50]
        name = await message.prompt("Save this prompt as:", title="Save prompt",
                                    value=current or first)
        name = str(name or "").strip()
        if not name:
            return
        if name != current and any(p.get("name") == name for p in self.saved):
            if not await message.confirm(f'A saved prompt called "{name}" already exists. '
                                         "Overwrite it?", title="Save prompt", ok_text="Overwrite"):
                return
        r = await Prompts().save_async(name, {k: f[k] for k in SAVED_PROMPT_FIELDS})
        if failed(r, "save the prompt"):
            return
        await self.load_saved(name)

    async def delete_prompt(self) -> None:
        name = str(by_id("saved-prompts").value)
        if not name or not await message.confirm(
                f'Delete the saved prompt "{name}"? The current text stays as it is.',
                title="Delete saved prompt", ok_text="Delete", danger=True):
            return
        r = await Prompts().delete_async(name)
        if failed(r, "delete the prompt"):
            return
        await self.load_saved("")
