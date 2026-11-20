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
    expected = case["active_prompt"]
    # The one deliberate change since the capture: Person mode moved from PhotoMaker to
    # PuLID-FLUX (2026-11-05), which has no trigger word, so the classic "img " prefix is gone.
    if state["mode"] == "person":
        assert expected.startswith("img ")
        expected = expected[len("img "):]
    assert active_prompt(state, state["mode"]) == expected


def test_golden_covers_every_mode():
    assert {c["state"]["mode"] for c in CASES} == {"generate", "person", "refine", "edit", "animate"}
