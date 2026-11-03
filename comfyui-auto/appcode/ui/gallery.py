"""The gallery and the shared "⋯" item menu — ports of the classic page's gallery code.

Gallery: collapsed it is a header strip; open, it takes over the workspace (the output area
hides). It is VIRTUALISED: `items` is the whole list and only the rows in view (plus
OVERSCAN) are built, so thousands of outputs cost what a few dozen do. Phase 0 measured
this in Python at ~1 ms per render. Tile geometry comes from CSS custom properties
(--gtile, --gitem-h, --ggap) so restyling keeps the row math right; tiles stay hard-sized.

Viewer (ui/viewer.py): clicking a tile opens the full-screen viewer on that file, with
previous / next, zoom and the same actions as the menu.

Item menu: ONE element on <body>, position: fixed — the gallery clips overflow and
virtualisation destroys tiles on scroll, so a menu anchored inside a tile would vanish.
Right-aligned to its button, flipped above when there is no room below; closes on an
outside click, Escape, scroll of either area, and resize. Actions: Download, Refine / Edit /
Animate (images only), Delete. Names travel as escaped data attributes, never as inline JS.
"""
from __future__ import annotations

import js

from wapyt import message

from bff.gallery import Gallery as GalleryApi
from ui.common import by_id, esc, failed, proxy
from ui.viewer import Viewer

VIDEO = (".mp4", ".gif", ".webm")
OVERSCAN = 2


def px(value) -> float:
    """JS parseFloat for CSS lengths: "140px" → 140.0 (Python's float() rejects the unit)."""
    s = str(value or "").strip()
    for unit in ("px", "rem", "em"):
        if s.endswith(unit):
            s = s[: -len(unit)]
            break
    try:
        return float(s)
    except ValueError:
        return 0.0


def is_video(name: str) -> bool:
    return name.lower().endswith(VIDEO)


def out_url(name: str) -> str:
    return "/outputs/" + str(js.encodeURIComponent(name))


def menu_button(name: str) -> str:
    return (f'<button type="button" class="item-menu-btn" data-name="{esc(name)}" '
            f'title="More actions" aria-label="More actions for {esc(name)}">⋯</button>')


def gallery_html() -> str:
    return ('<div class="gallery-section" id="gallery-section">'
            '<div class="gallery-header" id="gallery-header"><span class="gallery-title">Gallery</span>'
            '<span class="gallery-count" id="gallery-count">loading…</span>'
            '<span class="gallery-toggle-icon" id="gallery-icon">▼</span></div>'
            '<div class="gallery-grid" id="gallery-grid"><div class="gallery-sizer" id="gallery-sizer">'
            '<div class="inner" id="gallery-inner"></div></div></div></div>')


class ItemMenu:
    def __init__(self, on_send, on_delete) -> None:
        self.on_send, self.on_delete = on_send, on_delete
        self.anchor = None
        self.name = ""
        menu = js.document.createElement("div")
        menu.className, menu.id = "item-menu", "item-menu"
        js.document.body.appendChild(menu)
        menu.addEventListener("click", proxy(self._on_menu_click))
        js.document.addEventListener("click", proxy(self._on_doc_click))
        js.document.addEventListener("keydown", proxy(
            lambda e: self.close() if e.key == "Escape" else None))
        js.window.addEventListener("resize", proxy(lambda e: self.close()))

    def bind(self, container) -> None:
        """Delegate "⋯" clicks inside a container; scrolling it closes the menu."""
        container.addEventListener("click", proxy(self._on_btn_click))
        container.addEventListener("scroll", proxy(lambda e: self.close()))

    def _on_btn_click(self, ev) -> None:
        btn = ev.target.closest(".item-menu-btn")
        if not btn:
            return
        ev.stopPropagation()
        ev.preventDefault()
        if self.anchor is not None and self.anchor == btn:
            self.close()                                   # same button: toggle shut
        else:
            self.open(btn, str(btn.getAttribute("data-name")))

    def _on_doc_click(self, ev) -> None:
        t = ev.target
        if not t.closest(".item-menu") and not t.closest(".item-menu-btn"):
            self.close()

    def open(self, btn, name: str) -> None:
        self.close()
        self.name, self.anchor = name, btn
        rows = [f'<a href="{esc(out_url(name))}" download="{esc(name)}" data-act="download">'
                '<span class="mi-icon">↓</span>Download</a>']
        if not is_video(name):
            rows += [f'<button type="button" data-act="{a}"><span class="mi-icon">{i}</span>{lab}</button>'
                     for a, i, lab in (("refine", "✎", "Refine"), ("edit", "✦", "Edit"),
                                       ("animate", "▷", "Animate"))]
        rows += ['<div class="sep"></div>',
                 '<button type="button" class="danger" data-act="delete">'
                 '<span class="mi-icon">✕</span>Delete</button>']
        menu = by_id("item-menu")
        menu.innerHTML = "".join(rows)
        menu.classList.add("open")                         # show before measuring
        btn.classList.add("open")
        r = btn.getBoundingClientRect()
        w, h = menu.offsetWidth, menu.offsetHeight
        left, top = r.right - w, r.bottom + 4
        if top + h > js.window.innerHeight - 8:            # no room below: flip above
            top = max(8, r.top - h - 4)
        left = max(8, min(left, js.window.innerWidth - w - 8))
        menu.style.left, menu.style.top = f"{left}px", f"{top}px"

    def close(self) -> None:
        menu = by_id("item-menu")
        if menu:
            menu.classList.remove("open")
        if self.anchor is not None:
            self.anchor.classList.remove("open")
        self.anchor = None

    def _on_menu_click(self, ev) -> None:
        el = ev.target.closest("[data-act]")
        if not el:
            return
        act, name = str(el.getAttribute("data-act")), self.name
        # Close first: these switch mode or open a confirm, and a menu left hanging over
        # what they just filled in is exactly what the user would have to click away.
        self.close()
        if act in ("refine", "edit", "animate"):
            self.on_send(act, name)
        elif act == "delete":
            self.on_delete(name)


class GalleryView:
    def __init__(self, on_toggle=None) -> None:
        self.items: list[dict] = []
        self.is_open = False
        self.key = ""
        self.pending = False
        self.on_toggle = on_toggle or (lambda is_open: None)
        self.viewer: Viewer | None = None

    def mount(self, menu: ItemMenu) -> None:
        by_id("gallery-header").addEventListener("click", proxy(lambda e: self.toggle()))
        grid = by_id("gallery-grid")
        grid.addEventListener("scroll", proxy(lambda e: self.schedule(False)))
        grid.addEventListener("click", proxy(self._on_click))
        js.window.addEventListener("resize", proxy(lambda e: self._on_resize()))
        menu.bind(grid)
        # The viewer walks this list and reuses the menu's actions (send / delete).
        self.viewer = Viewer(lambda: self.items, menu.on_send, menu.on_delete)

    def _on_resize(self) -> None:
        self.key = ""
        self.schedule(True)

    def _on_click(self, ev) -> None:
        thumb = ev.target.closest(".gthumb")
        item = thumb.closest(".gallery-item") if thumb else None
        if item and not ev.target.closest(".item-menu-btn"):
            self.viewer.open(str(item.getAttribute("data-file")))

    # --- open / close -----------------------------------------------------------------
    def toggle(self) -> None:
        self.is_open = not self.is_open
        for el_id, cls in (("gallery-grid", "open"), ("gallery-icon", "open"),
                           ("gallery-section", "open")):
            by_id(el_id).classList.toggle(cls, self.is_open)
        by_id("workspace").classList.toggle("gallery-open", self.is_open)
        self.on_toggle(self.is_open)
        if self.is_open:
            self.key = ""
            from ui.common import spawn
            spawn(self.load(), "gallery")

    def close(self) -> None:
        if self.viewer is not None:
            self.viewer.close()
        if self.is_open:
            self.toggle()

    # --- data -------------------------------------------------------------------------
    async def load(self) -> None:
        r = await GalleryApi().items_async()
        self.items = list((r or {}).get("items") or [])
        self._count()
        self.key = ""
        self.render(True)

    def _count(self) -> None:
        n = len(self.items)
        by_id("gallery-count").textContent = f"{n} image{'' if n == 1 else 's'}"

    def forget(self, name: str) -> None:
        """Drop a deleted file from the list (the DOM holds only visible rows)."""
        self.items = [it for it in self.items if it.get("name") != name]
        self._count()
        self.render(True)
        if self.viewer is not None:
            self.viewer.removed(name)

    async def delete(self, name: str, on_removed) -> None:
        if not await message.confirm(
                f"Delete {name}?\n\nThis removes the file from outputs/ for good — there is no undo.",
                title="Delete output", ok_text="Delete", danger=True):
            return
        r = await GalleryApi().delete_async(name)
        if failed(r, f"delete {name}"):
            return
        # One file can be on screen twice (result card + tile): drop every match. Compared
        # in Python, not via an attribute selector, so no quoting to get wrong.
        for el in list(js.document.querySelectorAll("[data-file]")):
            if str(el.getAttribute("data-file")) == name:
                el.remove()
        self.forget(name)
        on_removed()

    # --- virtual window -----------------------------------------------------------------
    def schedule(self, force: bool) -> None:
        if self.pending:
            return
        self.pending = True

        def frame(_ts):
            self.pending = False
            self.render(force)

        js.requestAnimationFrame(proxy(frame))

    def render(self, force: bool = False) -> None:
        grid, sizer, inner = by_id("gallery-grid"), by_id("gallery-sizer"), by_id("gallery-inner")
        if not self.is_open or not grid.clientWidth:        # collapsed: width is 0
            return
        n = len(self.items)
        if not n:
            sizer.style.height = ""
            inner.innerHTML = '<div class="gallery-empty">No outputs yet.</div>'
            self.key = "empty"
            return
        root = js.getComputedStyle(js.document.documentElement)
        tile = px(root.getPropertyValue("--gtile"))
        item_h = px(root.getPropertyValue("--gitem-h"))
        gap = px(root.getPropertyValue("--ggap"))
        cs = js.getComputedStyle(grid)
        avail = grid.clientWidth - px(cs.paddingLeft) - px(cs.paddingRight)
        cols = max(1, int((avail + gap) // (tile + gap)))
        rows = -(-n // cols)
        row_h = item_h + gap
        sizer.style.height = f"{rows * row_h - gap}px"
        first = max(0, int(grid.scrollTop // row_h) - OVERSCAN)
        last = min(rows - 1, int((grid.scrollTop + grid.clientHeight) // row_h) + OVERSCAN)
        start, end = first * cols, min(n, (last + 1) * cols)
        key = f"{cols}:{start}:{end}"
        if key == self.key and not force:
            return
        self.key = key
        inner.style.gridTemplateColumns = f"repeat({cols}, {tile}px)"
        inner.style.transform = f"translateY({first * row_h}px)"
        inner.innerHTML = "".join(self._tile(it) for it in self.items[start:end])

    def _tile(self, item: dict) -> str:
        name = item["name"]
        url = esc(out_url(name))
        # Images load a small cached WebP (server.get_thumb); ?v=mtime makes it cacheable for
        # good and changes when the file does. Clicking opens the full image in the viewer.
        thumb = esc(f"/thumbs/{js.encodeURIComponent(name)}?v={int(item.get('mtime') or 0)}")
        media = (f'<video class="gthumb" src="{url}" data-url="{url}" muted preload="metadata" title="{esc(name)}"></video>'
                 if is_video(name) else
                 f'<img class="gthumb" src="{thumb}" data-url="{url}" alt="{esc(name)}" title="{esc(name)}" loading="lazy" decoding="async">')
        return (f'<div class="gallery-item" data-file="{esc(name)}">{media}'
                f'<span class="gname">{esc(name)}</span>{menu_button(name)}</div>')
