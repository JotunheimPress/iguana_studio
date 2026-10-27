"""BFF for saved prompts: data/saved-prompts.json through server.py's functions (the same
file the classic page used, so prompts saved before the switch-over are still there). Holds nothing between calls."""
from __future__ import annotations

from pytincture.dataclass import backend_for_frontend


def _detail(exc) -> str:
    return str(getattr(exc, "detail", None) or exc)


@backend_for_frontend
class Prompts:
    def all(self) -> dict:
        import server

        return {"ok": True, "prompts": server.list_prompts()["prompts"]}

    def save(self, name: str, fields: dict) -> dict:
        import server
        from fastapi import HTTPException

        try:
            server.save_prompt({"name": name, "fields": fields})
        except HTTPException as exc:
            return {"ok": False, "error": _detail(exc)}
        return {"ok": True}

    def delete(self, name: str) -> dict:
        import server
        from fastapi import HTTPException

        try:
            server.delete_prompt(name)
        except HTTPException as exc:
            if exc.status_code != 404:            # already gone is fine
                return {"ok": False, "error": _detail(exc)}
        return {"ok": True}
