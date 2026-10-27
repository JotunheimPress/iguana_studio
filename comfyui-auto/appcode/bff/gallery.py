"""BFF for the gallery: list and delete outputs, through server.py's own functions (one
definition of what is listable and deletable). Holds nothing between calls."""
from __future__ import annotations

from pytincture.dataclass import backend_for_frontend


@backend_for_frontend
class Gallery:
    def items(self) -> dict:
        """[{name, mtime, size}], newest first."""
        import server

        return {"ok": True, "items": server.gallery()}

    def delete(self, name: str) -> dict:
        import server
        from fastapi import HTTPException

        try:
            server.delete_output(str(name or ""))
        except HTTPException as exc:
            if exc.status_code != 404:            # already gone is the outcome we wanted
                return {"ok": False, "error": str(exc.detail)}
        return {"ok": True}
