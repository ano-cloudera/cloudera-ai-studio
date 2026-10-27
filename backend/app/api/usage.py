from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse

from app.services.usage_store import UsageStore


router = APIRouter(prefix="/usage", tags=["usage"])


def _store(request: Request) -> UsageStore:
    return request.app.state.usage_store


@router.get("/summary")
def usage_summary(
    request: Request,
    days: int = Query(7, ge=1, le=90),
    mtd: bool = Query(False),
) -> dict:
    store = _store(request)
    settings = request.app.state.settings
    totals = store.totals(days=None if mtd else days, mtd=mtd)
    budget = int(getattr(settings, "usage_monthly_token_budget", 0) or 0)
    window_days = days if not mtd else 31
    return {
        "period_days": days if not mtd else None,
        "mtd": mtd,
        "totals": totals,
        "mtd_totals": store.totals(mtd=True),
        "daily": store.daily_totals(days=window_days),
        "by_model": store.by_model(days=window_days),
        "monthly_token_budget": budget,
    }


@router.get("/events")
def usage_events(
    request: Request,
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    store = _store(request)
    return {"events": store.list_events(days=days, limit=limit, offset=offset)}


@router.get("/export.csv")
def usage_export_csv(request: Request, days: int = Query(30, ge=1, le=365)) -> PlainTextResponse:
    store = _store(request)
    body = store.export_csv(days=days)
    return PlainTextResponse(
        body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="llm-usage-{days}d.csv"'},
    )
