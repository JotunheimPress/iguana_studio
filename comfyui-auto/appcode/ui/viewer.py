"""The gallery's full-screen image viewer: clicking a tile opens it instead of a new tab.

One overlay on <body>, position: fixed, z-index 9000: above the page and the "⋯" menu, below
wapyt's modals (9600+) and toasts, so Delete's confirm still shows on top of it.

It walks the gallery's own list (`items()` is read fresh on every move, so a refresh or a
delete is picked up), tracked by index. Images zoom and pan with a CSS transform on the
<img> — translate(tx, ty) scale(s), origin top-left — and `s` is relative to the file's real
pixels, so the readout's 100% is 1:1. "Fit" fills the stage; zoom keeps the point under the
cursor (wheel) or the stage centre (buttons, keys) still. Videos get the browser's own
controls and no zoom.

Keys: ← → previous / next, Home / End first / last, + − zoom, 0 fit, 1 actual size,
Delete delete, Esc close. Double-click toggles fit ↔ 100% at that point.
"""
from __future__ import annotations

import js
from pyodide.ffi import to_js

from ui.common import by_id, esc, proxy

ZOOM_STEP = 1.25
ZOOM_MIN, ZOOM_MAX = 0.05, 16.0
VIDEO = (".mp4", ".webm")                   # a GIF is an <img>: it animates and zooms


def _url(name: str) -> str:
    return "/outputs/" + str(js.encodeURIComponent(name))


def _is_video(name: str) -> bool:
    return name.lower().endswith(VIDEO)


def _btn(act: str, label: str, title: str, cls: str = "") -> str:
    return (f'<button type="button" class="iv-btn {cls}" data-act="{act}" title="{esc(title)}" '
            f'aria-label="{esc(title)}">{label}</button>')


def _chevron(points: str) -> str:
    return ('<svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="{points}"/></svg>')


def viewer_html() -> str:
    zoom = (_btn("zoom-out", "−", "Zoom out (−)") + '<span class="iv-zoom" id="iv-zoom">100%</span>'
            + _btn("zoom-in", "+", "Zoom in (+)") + _btn("fit", "Fit", "Fit to window (0)", "iv-text")
            + _btn("actual", "1:1", "Actual size (1)", "iv-text"))
    acts = ('<a class="iv-btn iv-text" id="iv-download" data-act="download" title="Download">↓ Download</a>'
            + _btn("refine", "✎ Refine", "Refine this image", "iv-text iv-img-only")
            + _btn("edit", "✦ Edit", "Edit this image", "iv-text iv-img-only")
            + _btn("animate", "▷ Animate", "Animate this image", "iv-text iv-img-only")
            + _btn("tab", "↗", "Open in a new tab")
            + _btn("delete", "✕", "Delete (Del)", "danger"))
    return ('<div class="iv" id="iv" role="dialog" aria-modal="true" aria-label="Image viewer" hidden>'
            '<div class="iv-top"><span class="iv-count" id="iv-count"></span>'
            '<span class="iv-name" id="iv-name"></span><span class="iv-dims" id="iv-dims"></span>'
            + _btn("close", "×", "Close (Esc)", "iv-close") + '</div>'
            '<div class="iv-stage" id="iv-stage"><div class="iv-spin" id="iv-spin"></div></div>'
            + _btn("prev", _chevron("15 18 9 12 15 6"), "Previous (←)", "iv-nav iv-prev")
            + _btn("next", _chevron("9 18 15 12 9 6"), "Next (→)", "iv-nav iv-next")
            + f'<div class="iv-bar"><div class="iv-group iv-zoom-group">{zoom}</div>'
            f'<div class="iv-group">{acts}</div></div></div>')


class Viewer:
    def __init__(self, items, on_send, on_delete) -> None:
        """`items()` → the gallery's list; `on_send(act, name)`; `on_delete(name)` (confirms)."""
        self.items, self.on_send, self.on_delete = items, on_send, on_delete
        self.index = 0
        self.name = ""
        self.media = None
        self.nat_w = self.nat_h = 0
        self.scale, self.tx, self.ty = 1.0, 0.0, 0.0
        self.fitted = True
        self.drag = None                                    # (pointer id, x, y, tx, ty)

        holder = js.document.createElement("div")
        holder.innerHTML = viewer_html()
        self.el = holder.firstElementChild
        js.document.body.appendChild(self.el)
        self.stage = by_id("iv-stage")

        # One handler pair for every image: a proxy per image would never be freed.
        self._load_proxy = proxy(self._loaded)
        self._error_proxy = proxy(self._failed)
        self.el.addEventListener("click", proxy(self._on_click))
        js.document.addEventListener("keydown", proxy(self._on_key))
        js.window.addEventListener("resize", proxy(lambda e: self._refit()))
        opts = to_js({"passive": False}, dict_converter=js.Object.fromEntries)
        self.stage.addEventListener("wheel", proxy(self._on_wheel), opts)
        self.stage.addEventListener("dblclick", proxy(self._on_dblclick))
        self.stage.addEventListener("pointerdown", proxy(self._on_down))
        self.stage.addEventListener("pointermove", proxy(self._on_move))
        for ev in ("pointerup", "pointercancel"):
            self.stage.addEventListener(ev, proxy(self._on_up))

    # --- open / close / move ------------------------------------------------------------
    @property
    def is_open(self) -> bool:
        return not self.el.hidden

    def open(self, name: str) -> None:
        names = [it.get("name") for it in self.items()]
        self.index = names.index(name) if name in names else 0
        self.el.hidden = False
        js.document.body.classList.add("iv-lock")
        self._show()

    def close(self) -> None:
        if not self.is_open:
            return
        self.el.hidden = True
        js.document.body.classList.remove("iv-lock")
        if self.media is not None:
            self.media.remove()                             # stops a playing video
            self.media = None

    def step(self, delta: int) -> None:
        n = len(self.items())
        if n:
            self.index = (self.index + delta) % n           # wraps at either end
            self._show()

    def go(self, index: int) -> None:
        if self.items():
            self.index = max(0, min(index, len(self.items()) - 1))
            self._show()

    def removed(self, name: str) -> None:
        """The gallery dropped `name`: stay at the same index, now the next image."""
        if not self.is_open or name != self.name:
            return
        if not self.items():
            self.close()
        else:
            self.go(self.index)

    def _show(self) -> None:
        items = self.items()
        if not items:
            self.close()
            return
        self.index = max(0, min(self.index, len(items) - 1))
        self.name = name = str(items[self.index].get("name"))
        video = _is_video(name)
        url = _url(name)
        by_id("iv-count").textContent = f"{self.index + 1} / {len(items)}"
        by_id("iv-name").textContent = name
        by_id("iv-name").title = name
        by_id("iv-dims").textContent = ""
        dl = by_id("iv-download")
        dl.href, dl.download = url, name
        self.el.classList.toggle("iv-video", video)
        for el in self.el.querySelectorAll(".iv-nav"):
            el.hidden = len(items) < 2

        if self.media is not None:
            self.media.remove()
        self.stage.classList.add("loading")
        if video:
            media = js.document.createElement("video")
            media.controls = media.loop = media.autoplay = True
            media.addEventListener("loadedmetadata", self._load_proxy)
        else:
            media = js.document.createElement("img")
            media.alt = name
            media.draggable = False
            media.addEventListener("load", self._load_proxy)
        media.className = "iv-media"
        media.addEventListener("error", self._error_proxy)
        self.media = media
        media.src = url
        self.stage.appendChild(media)
        self._preload(items)

    def _loaded(self, ev) -> None:
        media = ev.target
        if self.media is None or media != self.media:     # an older image finished late
            return
        self.stage.classList.remove("loading")
        if _is_video(self.name):
            self.nat_w, self.nat_h = media.videoWidth, media.videoHeight
        else:
            self.nat_w, self.nat_h = media.naturalWidth, media.naturalHeight
        if self.nat_w and self.nat_h:
            by_id("iv-dims").textContent = f"{self.nat_w} × {self.nat_h}"
        self.fit()

    def _failed(self, ev) -> None:
        if self.media is not None and ev.target == self.media:
            self.stage.classList.remove("loading")
            by_id("iv-dims").textContent = "could not load"

    def _preload(self, items) -> None:
        """Warm the browser cache for both neighbours so ← → feel instant."""
        n = len(items)
        for d in (1, -1):
            if n > 1:
                other = str(items[(self.index + d) % n].get("name"))
                if not _is_video(other):
                    js.Image.new().src = _url(other)

    # --- zoom / pan ---------------------------------------------------------------------
    def _fit_scale(self) -> float:
        if not (self.nat_w and self.nat_h):
            return 1.0
        return min(self.stage.clientWidth / self.nat_w, self.stage.clientHeight / self.nat_h)

    def fit(self) -> None:
        self.fitted = True
        self._set_scale(self._fit_scale(), None)

    def _refit(self) -> None:
        if self.is_open:
            self.fit() if self.fitted else self._apply()

    def zoom(self, factor: float, at=None) -> None:
        self.fitted = False
        self._set_scale(self.scale * factor, at)

    def actual(self, at=None) -> None:
        self.fitted = False
        self._set_scale(1.0, at)

    def _set_scale(self, scale: float, at) -> None:
        """Change scale keeping the stage point `at` (x, y) still; None = the centre."""
        if _is_video(self.name) or not self.nat_w:
            return
        scale = max(ZOOM_MIN, min(ZOOM_MAX, scale))
        w, h = self.stage.clientWidth, self.stage.clientHeight
        px, py = at if at else (w / 2, h / 2)
        ratio = scale / self.scale
        self.tx = px - (px - self.tx) * ratio
        self.ty = py - (py - self.ty) * ratio
        self.scale = scale
        self._apply()

    def _apply(self) -> None:
        """Clamp the pan (a small side is centred, a big one may not leave a gap) and draw."""
        if self.media is None or _is_video(self.name):
            return
        w, h = self.stage.clientWidth, self.stage.clientHeight
        iw, ih = self.nat_w * self.scale, self.nat_h * self.scale
        self.tx = (w - iw) / 2 if iw <= w else min(0.0, max(w - iw, self.tx))
        self.ty = (h - ih) / 2 if ih <= h else min(0.0, max(h - ih, self.ty))
        self.media.style.width, self.media.style.height = f"{self.nat_w}px", f"{self.nat_h}px"
        self.media.style.transform = f"translate({self.tx}px, {self.ty}px) scale({self.scale})"
        self.stage.classList.toggle("pannable", iw > w + 0.5 or ih > h + 0.5)
        by_id("iv-zoom").textContent = f"{round(self.scale * 100)}%"

    def _stage_point(self, ev):
        r = self.stage.getBoundingClientRect()
        return ev.clientX - r.left, ev.clientY - r.top

    def _on_wheel(self, ev) -> None:
        ev.preventDefault()
        self.zoom(ZOOM_STEP if ev.deltaY < 0 else 1 / ZOOM_STEP, self._stage_point(ev))

    def _on_dblclick(self, ev) -> None:
        if not _is_video(self.name):
            self.fit() if not self.fitted else self.actual(self._stage_point(ev))

    def _on_down(self, ev) -> None:
        if _is_video(self.name) or ev.button != 0 or not self.stage.classList.contains("pannable"):
            return
        self.drag = (ev.pointerId, ev.clientX, ev.clientY, self.tx, self.ty)
        self.stage.setPointerCapture(ev.pointerId)
        self.stage.classList.add("dragging")

    def _on_move(self, ev) -> None:
        if self.drag is None or ev.pointerId != self.drag[0]:
            return
        _, x0, y0, tx0, ty0 = self.drag
        self.tx, self.ty = tx0 + ev.clientX - x0, ty0 + ev.clientY - y0
        self.fitted = False
        self._apply()

    def _on_up(self, ev) -> None:
        if self.drag is not None and ev.pointerId == self.drag[0]:
            self.drag = None
            self.stage.classList.remove("dragging")

    # --- buttons / keys -----------------------------------------------------------------
    def _on_click(self, ev) -> None:
        el = ev.target.closest("[data-act]")
        if not el:
            return
        act = str(el.getAttribute("data-act"))
        if act == "download":
            return                                          # the <a download> does it
        ev.preventDefault()
        self._do(act)

    def _do(self, act: str) -> None:
        name = self.name
        if act == "close":
            self.close()
        elif act in ("prev", "next"):
            self.step(-1 if act == "prev" else 1)
        elif act == "zoom-in":
            self.zoom(ZOOM_STEP)
        elif act == "zoom-out":
            self.zoom(1 / ZOOM_STEP)
        elif act == "fit":
            self.fit()
        elif act == "actual":
            self.actual()
        elif act == "tab":
            js.window.open(_url(name), "_blank", "noopener")
        elif act in ("refine", "edit", "animate") and not _is_video(name):
            self.close()
            self.on_send(act, name)
        elif act == "delete":
            self.on_delete(name)                            # confirms; removed() follows

    def _on_key(self, ev) -> None:
        if not self.is_open or ev.ctrlKey or ev.metaKey or ev.altKey:
            return
        if js.document.querySelector(".wapyt-msg-overlay, .wapyt-modal-overlay"):
            return                                          # a dialog on top owns the keys
        act = {"Escape": "close", "ArrowLeft": "prev", "ArrowRight": "next",
               "+": "zoom-in", "=": "zoom-in", "-": "zoom-out", "_": "zoom-out",
               "0": "fit", "1": "actual", "Delete": "delete"}.get(str(ev.key))
        if str(ev.key) in ("Home", "End"):
            ev.preventDefault()
            self.go(0 if ev.key == "Home" else len(self.items()) - 1)
        elif act:
            ev.preventDefault()
            ev.stopPropagation()
            self._do(act)
