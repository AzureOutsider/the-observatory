import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, holdings, knowledge, market, system, transactions, watchlists
from app.config import settings
from app.db import SessionLocal, init_db
from app.observability import RequestMetricsMiddleware
from app.services.news import prune_old_news
from app.services.portfolio_valuation import CLOSE_TIME, refresh_closed_portfolio

logger = logging.getLogger(__name__)
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    _prune_news_once()
    scheduler = asyncio.create_task(_portfolio_close_scheduler())
    try:
        yield
    finally:
        scheduler.cancel()
        await asyncio.gather(scheduler, return_exceptions=True)


async def _portfolio_close_scheduler() -> None:
    """Run close valuation in the background while the local website is open."""
    while True:
        now = datetime.now(SHANGHAI_TZ)
        if now.weekday() < 5 and now.time() >= CLOSE_TIME:
            try:
                await asyncio.to_thread(_run_close_valuation_once)
            except Exception:
                logger.exception("portfolio close valuation failed")
            await asyncio.sleep(600)
        else:
            await asyncio.sleep(60 if now.weekday() < 5 else 3600)


def _run_close_valuation_once() -> None:
    session = SessionLocal()
    try:
        refresh_closed_portfolio(session)
    finally:
        session.close()


def _prune_news_once() -> None:
    """Drop news outside the retention window once at startup."""
    session = SessionLocal()
    try:
        deleted = prune_old_news(session)
        if deleted:
            logger.info("pruned %d news items outside retention window", deleted)
    except Exception:
        logger.exception("news retention pruning failed")
    finally:
        session.close()


def create_app() -> FastAPI:
    app = FastAPI(title="The Observatory API", lifespan=lifespan)
    app.add_middleware(RequestMetricsMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(holdings.router, prefix="/api")
    app.include_router(transactions.router, prefix="/api")
    app.include_router(watchlists.router, prefix="/api")
    app.include_router(market.router, prefix="/api")
    app.include_router(knowledge.router, prefix="/api")
    app.include_router(agent.router, prefix="/api")
    app.include_router(system.router, prefix="/api")
    return app


app = create_app()
