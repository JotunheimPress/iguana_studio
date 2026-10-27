"""Prompt composition matches the classic page — forever, without a browser.

tests/prompt_golden.json holds 200 random sidebar states (real modifier values; blank,
whitespace, comma, quote, newline and unicode text; all five modes) with the prompt the
classic page's buildPrompt()/activePrompt() produced for each, captured before that page
was deleted (PYTINCTURE_PLAN.md Phase 5). ui/prompt.py must reproduce every one.

    .venv/bin/python -m pytest -q tests
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "appcode"))
from ui.prompt import active_prompt  # noqa: E402

CASES = json.loads((ROOT / "tests" / "prompt_golden.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[f"{i}-{c['state']['mode']}" for i, c in enumerate(CASES)])
def test_matches_classic(case):
    state = case["state"]
    assert active_prompt(state, state["mode"]) == case["active_prompt"]


def test_golden_covers_every_mode():
    assert {c["state"]["mode"] for c in CASES} == {"generate", "person", "refine", "edit", "animate"}
