from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("code", "asset_type", name="uq_asset_code_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    # Official name resolved from the market source; custom_name is presentation-only.
    custom_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(32), default="fund")
    market: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    theme: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    holdings: Mapped[list["Holding"]] = relationship(back_populates="asset")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="asset")
    snapshots: Mapped[list["PriceSnapshot"]] = relationship(back_populates="asset")
    daily_bars: Mapped[list["DailyBar"]] = relationship(back_populates="asset")


class Holding(TimestampMixin, Base):
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    units: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    cost_basis: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    profit: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    last_valuation_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_valuation_source: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    last_manual_adjustment_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_manual_adjustment_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_update_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    asset: Mapped[Asset] = relationship(back_populates="holdings")

    @property
    def manual_adjusted(self) -> bool:
        return self.last_manual_adjustment_at is not None


class PortfolioValuationRun(Base):
    __tablename__ = "portfolio_valuation_runs"
    __table_args__ = (UniqueConstraint("valuation_date", name="uq_portfolio_valuation_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    valuation_date: Mapped[date] = mapped_column(Date, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_count: Mapped[int] = mapped_column(default=0)
    failed_count: Mapped[int] = mapped_column(default=0)


class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    operation: Mapped[str] = mapped_column(String(32))
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    units: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    fee: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retracted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    retraction_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retraction_effect: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    asset: Mapped[Asset] = relationship(back_populates="transactions")


class Watchlist(TimestampMixin, Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="watchlist",
        cascade="all, delete-orphan",
    )


class WatchlistItem(TimestampMixin, Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "asset_id", name="uq_watchlist_asset"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    tags_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    watchlist: Mapped[Watchlist] = relationship(back_populates="items")
    asset: Mapped[Asset] = relationship()


class PriceSnapshot(TimestampMixin, Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (
        Index(
            "ix_price_snapshots_asset_source_observed_at",
            "asset_id",
            "source",
            "observed_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    source: Mapped[str] = mapped_column(String(80))
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    raw_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    asset: Mapped[Asset] = relationship(back_populates="snapshots")


class DailyBar(TimestampMixin, Base):
    __tablename__ = "daily_bars"
    __table_args__ = (UniqueConstraint("asset_id", "bar_date", name="uq_asset_bar_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    bar_date: Mapped[date] = mapped_column(Date, index=True)
    open_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    high_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    low_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    close_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)
    source: Mapped[str] = mapped_column(String(80))

    asset: Mapped[Asset] = relationship(back_populates="daily_bars")


class NewsItem(TimestampMixin, Base):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    source: Mapped[str] = mapped_column(String(80))
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    importance: Mapped[Optional[int]] = mapped_column(nullable=True)
    tags_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    quality: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    relevance: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class KnowledgeChunk(TimestampMixin, Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    content: Mapped[str] = mapped_column(Text)
    source_path: Mapped[str] = mapped_column(String(1000))


class AgentNote(TimestampMixin, Base):
    __tablename__ = "agent_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    note_date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(80), default="agent")
