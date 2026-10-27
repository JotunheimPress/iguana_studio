"""Prompt composition — a line-for-line port of the classic page's buildPrompt()/activePrompt().

Runs in the browser (and imports nothing browser-only, so it is testable anywhere). The
order is fixed in code and independent of the sidebar's visual order; the manual text
leads because diffusion models weight early tokens more. tests/test_prompt_parity.py checks
this against the classic page's JavaScript.
"""
from __future__ import annotations

# The sidebar fields a prompt is built from, in the classic page's order.
PROMPT_FIELDS = [
    "f-extra",
    "f-eyes", "f-expression",
    "f-clothing", "f-setting", "f-lighting", "f-style", "f-camera",
    "f-pose", "f-focus",
]
# What a saved prompt holds: the sidebar plus the negative (not model/LoRAs/sampler).
SAVED_PROMPT_FIELDS = [*PROMPT_FIELDS, "neg-prompt"]

# Modes whose prompt does not come from the sidebar, and what the preview says instead.
SIDEBAR_UNUSED = {
    "edit": "Edit uses the Instruction box — the sidebar is not used.",
    "animate": "Animate uses the Motion box — the sidebar is not used.",
}


def _get(fields: dict, key: str) -> str:
    return str(fields.get(key) or "").strip()


def build_prompt(fields: dict, mode: str = "generate") -> str:
    parts = []
    manual = _get(fields, "f-extra")
    if manual:
        parts.append(manual)
    expr = _get(fields, "f-expression")
    if expr:
        parts.append(expr)
    eyes = _get(fields, "f-eyes")
    if eyes:
        parts.append(eyes + " eyes")
    clothing = _get(fields, "f-clothing")
    if clothing:
        parts.append("wearing " + clothing)
    # Setting values carry their own preposition ("on a beach") — pushed verbatim.
    setting = _get(fields, "f-setting")
    if setting:
        parts.append(setting)
    for key in ("f-lighting", "f-style", "f-camera", "f-pose", "f-focus"):
        v = _get(fields, key)
        if v:
            parts.append(v)
    prompt = ", ".join(parts)
    # Person mode: the PhotoMaker trigger word (even on an empty prompt, like the JS).
    if mode == "person":
        prompt = "img " + prompt
    return prompt


def active_prompt(fields: dict, mode: str) -> str:
    """What this mode actually sends. Edit and Animate carry their own box."""
    if mode == "edit":
        return _get(fields, "k-instruction")
    if mode == "animate":
        return _get(fields, "v-motion")
    return build_prompt(fields, mode)
