"""The LoRA stack in the rail — a port of the classic page's renderLoras()/activeLoras().

A stack is a chain, not a set: entry N patches the model entry N−1 already patched, so the
rows are numbered and reordered with ↑/↓. One strength slider (−1…2) drives both model and
clip strength. A saved entry whose file is no longer installed is KEPT and flagged (silently
snapping it to another LoRA would generate the wrong image quietly) but left out of what is
sent. The stack persists in `studio_v1` under `__loras`, shared with the classic page.

Only the checkpoint-based modes take LoRAs (LORA_MODES); the page hides the section otherwise.
"""
from __future__ import annotations

from bff.studio import Studio
from ui.common import by_id, esc, load_state, proxy, save_state

LORA_MODES = ("generate", "person", "refine")


def label(filename: str) -> str:
    import re

    return re.sub(r"[_-]+", " ", re.sub(r"\.(safetensors|ckpt|pt|bin)$", "", filename, flags=re.I))


def loras_html() -> str:
    return ('<div id="lora-section"><div class="section-label">LoRAs</div>'
            '<div id="lora-list"></div>'
            '<button class="lora-add" id="lora-add" type="button">+ Add LoRA</button>'
            '<div class="lora-note" id="lora-note"></div></div>')


class LoraStack:
    def __init__(self) -> None:
        self.options: list[str] = []
        stack = load_state().get("__loras")
        self.stack: list[dict] = [
            {"name": str(e.get("name") or ""), "strength": float(e.get("strength", 0.8))}
            for e in (stack if isinstance(stack, list) else []) if isinstance(e, dict)]

    def mount(self) -> None:
        by_id("lora-add").addEventListener("click", proxy(lambda e: self.add()))
        lst = by_id("lora-list")
        lst.addEventListener("click", proxy(self._on_click))
        lst.addEventListener("change", proxy(self._on_change))
        lst.addEventListener("input", proxy(self._on_input))
        self.render()

    async def load(self) -> None:
        r = await Studio().loras_async()
        self.options = list((r or {}).get("loras") or [])
        self.render()

    def _save(self) -> None:
        save_state({"__loras": self.stack})

    def active(self) -> list[dict]:
        """What goes on the wire: named, installed entries only, in chain order."""
        return [{"name": e["name"], "strength": e["strength"]}
                for e in self.stack if e["name"] and e["name"] in self.options]

    def add(self) -> None:
        if self.options:
            self.stack.append({"name": self.options[0], "strength": 0.8})
            self.render()
            self._save()

    # --- events (delegated: rows are re-rendered wholesale) ---------------------------
    def _row(self, ev) -> int:
        row = ev.target.closest(".lora-row")
        return int(row.getAttribute("data-i")) if row else -1

    def _on_click(self, ev) -> None:
        btn = ev.target.closest("button")
        i = self._row(ev)
        if not btn or i < 0:
            return
        act = str(btn.getAttribute("data-act"))
        if act == "del":
            self.stack.pop(i)
        elif act in ("up", "down"):
            j = i + (-1 if act == "up" else 1)
            if 0 <= j < len(self.stack):
                self.stack[i], self.stack[j] = self.stack[j], self.stack[i]
        self.render()
        self._save()

    def _on_change(self, ev) -> None:
        i = self._row(ev)
        if i < 0:
            return
        if ev.target.tagName == "SELECT":
            self.stack[i]["name"] = str(ev.target.value)
            self.render()
        self._save()                              # also the range's final value

    def _on_input(self, ev) -> None:
        i = self._row(ev)
        if i >= 0 and ev.target.type == "range":
            self.stack[i]["strength"] = float(ev.target.value)
            ev.target.nextElementSibling.textContent = f"{self.stack[i]['strength']:.2f}"

    # --- render ------------------------------------------------------------------------
    def render(self) -> None:
        rows = []
        n = len(self.stack)
        for i, e in enumerate(self.stack):
            opts = ""
            if e["name"] not in self.options:
                text = f'{e["name"]} (missing)' if e["name"] else "— pick a LoRA —"
                opts += f'<option value="{esc(e["name"])}">{esc(text)}</option>'
            opts += "".join(f'<option value="{esc(o)}"{" selected" if o == e["name"] else ""}>'
                            f'{esc(label(o))}</option>' for o in self.options)
            rows.append(
                f'<div class="lora-row" data-i="{i}"><div class="lora-row-top">'
                f'<span class="lora-ord">{i + 1}.</span><select>{opts}</select>'
                f'<button class="lora-move" type="button" data-act="up" title="Apply earlier"{" disabled" if i == 0 else ""}>↑</button>'
                f'<button class="lora-move" type="button" data-act="down" title="Apply later"{" disabled" if i == n - 1 else ""}>↓</button>'
                '<button class="lora-x" type="button" data-act="del" title="Remove">✕</button></div>'
                '<div class="lora-strength"><span class="lora-ord">Strength</span>'
                f'<input type="range" min="-1" max="2" step="0.05" value="{e["strength"]}">'
                f'<span class="val">{e["strength"]:.2f}</span></div></div>')
        by_id("lora-list").innerHTML = "".join(rows)
        add = by_id("lora-add")
        none = not self.options
        add.disabled = none
        add.textContent = "No LoRAs installed" if none else "+ Add LoRA"
        missing = [e for e in self.stack if e["name"] and e["name"] not in self.options]
        by_id("lora-note").textContent = (
            "Drop .safetensors files into ComfyUI/models/loras/ and reload." if none else
            f"{len(missing)} saved LoRA{'s are' if len(missing) > 1 else ' is'} no longer installed."
            if missing else
            "Applied top to bottom. Most LoRAs need their trigger word in the prompt." if self.stack
            else "")
