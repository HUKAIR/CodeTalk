"""Optional FastAPI adapters for the existing local review contract."""
from fastapi import APIRouter, Body
from fastapi.responses import HTMLResponse, JSONResponse

from .cache import Cache
from .config import redact_data
from .review import build_review_cards
from .review_feedback import build_feedback
from .review_web import _validated_judgment, render_review_html


def review_router(project_resolver, cache_path):
    router = APIRouter()

    @router.get("/review")
    def review_page(project: str | None = None):
        pp = project_resolver(project)
        cards, error, _ = build_review_cards(pp, cache_path=cache_path())
        if error:
            return JSONResponse({"error": "review unavailable"}, status_code=400)
        with Cache(cache_path()) as cache:
            judgments = cache.get_review_judgments(str(pp))
        return HTMLResponse(render_review_html(pp.name, cards, judgments, workspace=True))

    @router.post("/judgment")
    def judgment(payload: dict = Body(...), project: str | None = None):
        pp = project_resolver(project)
        cards, error, _ = build_review_cards(pp, cache_path=cache_path())
        if error:
            return JSONResponse({"error": "review unavailable"}, status_code=400)
        record, status, error = _validated_judgment(payload, {c["id"] for c in cards})
        if error:
            return JSONResponse({"error": error}, status_code=status)
        try:
            with Cache(cache_path()) as cache:
                cache.put_review_judgment(str(pp), record["card_id"], record["status"],
                                          record["action_changed"], record["elapsed_seconds"])
                saved = cache.get_review_judgments(str(pp))[record["card_id"]]
        except Exception:  # noqa: BLE001 - same failure contract as the stdlib server
            return JSONResponse({"error": "judgment not saved"}, status_code=500)
        return JSONResponse(redact_data({"ok": True, "judgment": saved}))

    def feedback(payload, project, export=False):
        pp = project_resolver(project)
        cards, error, _ = build_review_cards(pp, cache_path=cache_path())
        if error:
            return JSONResponse({"error": "review unavailable"}, status_code=400)
        card = next((c for c in cards if c["id"] == payload.get("card_id")), None)
        if card is None:
            return JSONResponse({"error": "unknown card"}, status_code=404)
        try:
            with Cache(cache_path()) as cache:
                saved = cache.get_review_judgments(str(pp)).get(card["id"])
            if not saved:
                return JSONResponse({"error": "resolve card before feedback"}, status_code=409)
            result = build_feedback(card, saved, approved_comment=payload.get("approved_comment"))
        except ValueError:
            return JSONResponse({"error": "invalid feedback"}, status_code=400)
        except Exception:  # noqa: BLE001 - never expose local cache exception details
            return JSONResponse({"error": "feedback unavailable"}, status_code=500)
        headers = {"Content-Disposition": 'attachment; filename="codetalk-review-feedback.json"'} if export else None
        return JSONResponse(redact_data(result if export else {"feedback": result}), headers=headers)

    @router.post("/feedback/preview")
    def preview(payload: dict = Body(...), project: str | None = None):
        return feedback(payload, project)

    @router.post("/feedback/export")
    def export(payload: dict = Body(...), project: str | None = None):
        return feedback(payload, project, export=True)

    return router
