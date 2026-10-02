from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.services.frontier_news import available_news_tags, fetch_frontier_news
from app.services.portfolio_market import get_holding_fund_trends, refresh_holding_fund_trends
from app.services.market import fetch_fund_estimate, fetch_market_indices, fetch_news
from app.services.market_health import get_source_health
from app.services.portfolio_valuation import refresh_closed_portfolio

router = APIRouter(tags=["market"])


@router.get("/market/indices")
def market_indices():
    return fetch_market_indices()


@router.get("/market/funds/{code}/estimate")
def fund_estimate(code: str):
    return fetch_fund_estimate(code)


@router.get("/market/holdings/today")
def holding_fund_trends(refresh: bool = True, session: Session = Depends(get_session)):
    if refresh:
        return refresh_holding_fund_trends(session)
    return get_holding_fund_trends(session)


@router.post("/market/holdings/close-valuation")
def close_valuation(force: bool = False, session: Session = Depends(get_session)):
    """Manually inspect or trigger the once-daily post-close valuation."""
    return refresh_closed_portfolio(session, force=force)


@router.get("/market/data-sources/health")
def market_data_sources_health():
    return get_source_health()


@router.get("/news")
def news(limit: int = 20, refresh: bool = False, session: Session = Depends(get_session)):
    return fetch_news(limit=limit, refresh=refresh, session=session)


@router.get("/frontier-news")
def frontier_news(
    limit: int = 40,
    tag: str | None = None,
    refresh: bool = False,
    session: Session = Depends(get_session),
):
    return fetch_frontier_news(limit=limit, tag=tag, session=session, refresh=refresh)


@router.get("/frontier-news/tags")
def frontier_news_tags():
    return ["全部", *available_news_tags()]
