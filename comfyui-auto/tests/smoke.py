"""Smoke test: open every mode, the gallery and its menu; fail on any browser console error.

    IGUANA_URL=http://127.0.0.1:7862 CHROME=…/chrome uv run --with playwright python tests/smoke.py
    SMOKE_GENERATE=1 …   # also run one real FLUX generation (needs ComfyUI + the GGUF)

Screenshots land in tests/shots/ (git-ignored). Read-only unless SMOKE_GENERATE is set,
and then it deletes the image it made.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

URL = os.environ.get("IGUANA_URL", "http://127.0.0.1:7862")
CHROME = os.environ.get("CHROME") or None
SHOTS = Path(__file__).resolve().parent / "shots"
MODES = ["generate", "person", "refine", "edit", "animate"]


async def viewer_checks(pg, problems: list[str]) -> None:
    """Tile click → viewer; → steps; + zooms; 0 fits; Esc closes. Read-only."""
    first = await pg.get_attribute(".gallery-item >> nth=0", "data-file")
    await pg.click(".gallery-item >> nth=0 >> .gthumb")
    if not await pg.is_visible("#iv"):
        problems.append("viewer did not open on a tile click")
        return
    if await pg.text_content("#iv-name") != first:
        problems.append(f"viewer opened {await pg.text_content('#iv-name')!r}, not {first!r}")
    await pg.wait_for_function("!document.getElementById('iv-stage').classList.contains('loading')",
                               timeout=20_000)
    await pg.screenshot(path=str(SHOTS / "viewer.png"))
    fit = await pg.text_content("#iv-zoom")
    await pg.keyboard.press("+")
    if await pg.text_content("#iv-zoom") == fit:
        problems.append("viewer: + did not zoom")
    await pg.keyboard.press("0")
    if await pg.text_content("#iv-zoom") != fit:
        problems.append("viewer: 0 did not return to fit")
    if await pg.locator(".gallery-item").count() > 1:
        await pg.keyboard.press("ArrowRight")
        if (await pg.text_content("#iv-count") or "").split(" / ")[0] != "2":
            problems.append("viewer: → did not move to the next item")
        await pg.click("#iv .iv-prev")
        if await pg.text_content("#iv-name") != first:
            problems.append("viewer: ‹ did not come back")
    await pg.keyboard.press("Escape")
    if await pg.is_visible("#iv"):
        problems.append("viewer did not close on Escape")


async def main() -> int:
    SHOTS.mkdir(exist_ok=True)
    problems: list[str] = []
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME)
        pg = await b.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.on("console", lambda m: m.type == "error" and errors.append(f"console: {m.text}"))

        for path, want in (("/api/health", 200), ("/", 200)):
            r = await pg.request.get(URL + path)
            if r.status != want:
                problems.append(f"GET {path} → {r.status}")
        r = await pg.request.get(URL + "/api/health", headers={"Host": "evil.example"})
        if r.status != 400:
            problems.append(f"foreign Host header → {r.status}, expected 400")

        t0 = time.time()
        await pg.goto(URL + "/")                                # redirects to /iguana/
        await pg.wait_for_selector("#prompt-preview", timeout=180_000)
        await pg.wait_for_function("document.querySelectorAll('#g-checkpoint option').length > 1",
                                   timeout=60_000)
        print(f"boot: {time.time() - t0:.1f}s at {pg.url}")
        print("ComfyUI:", await pg.text_content("#status-label"))

        for mode in MODES:
            await pg.click(f'.mode-tab[data-mode="{mode}"]')
            await pg.wait_for_timeout(300)
            if not await pg.is_visible(f"#ctrl-{mode}"):
                problems.append(f"{mode}: control bar not visible")
            await pg.screenshot(path=str(SHOTS / f"mode-{mode}.png"))
        await pg.click('.mode-tab[data-mode="generate"]')

        await pg.click("#gallery-header")
        await pg.wait_for_function("document.getElementById('gallery-inner').children.length > 0",
                                   timeout=20_000)
        await pg.screenshot(path=str(SHOTS / "gallery.png"))
        if await pg.locator(".gallery-item").count():
            await pg.hover(".gallery-item >> nth=0")
            await pg.click(".gallery-item >> nth=0 >> .item-menu-btn")
            if not await pg.is_visible("#item-menu"):
                problems.append("item menu did not open")
            await pg.keyboard.press("Escape")
            if await pg.is_visible("#item-menu"):
                problems.append("item menu did not close on Escape")
            await viewer_checks(pg, problems)
        await pg.click("#gallery-header")

        if os.environ.get("SMOKE_GENERATE"):
            await pg.select_option("#g-checkpoint", "flux1-schnell-Q4_K_S.gguf")
            await pg.fill("#g-width", "512")
            await pg.fill("#g-height", "512")
            await pg.click("#sb-clear")
            await pg.fill("#f-extra", "smoke test: a small red cube on a white table")
            n0 = await pg.locator(".output-card").count()
            t0 = time.time()
            await pg.click("#top-gen-btn")
            await pg.wait_for_function(
                f"document.querySelectorAll('.output-card').length > {n0} || document.querySelector('.error-card')",
                timeout=300_000)
            err = await pg.evaluate("document.querySelector('.error-card')?.textContent || ''")
            if err:
                problems.append(f"generation failed: {err}")
            else:
                name = await pg.evaluate("document.querySelector('.output-card').dataset.file")
                print(f"generated {name} in {time.time() - t0:.1f}s")
                await pg.screenshot(path=str(SHOTS / "generated.png"))
                await pg.hover(".output-card >> nth=0")
                await pg.click(".output-card >> nth=0 >> .item-menu-btn")
                await pg.click("#item-menu [data-act=delete]")
                await pg.click(".wapyt-msg-btn-primary")
                await pg.wait_for_timeout(1000)

        await b.close()
    problems += errors
    for line in problems:
        print("FAIL:", line)
    print("PASS" if not problems else f"FAIL ({len(problems)})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
