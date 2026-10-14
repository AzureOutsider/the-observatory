from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AssetRead(BaseModel):
    id: int
    code: str
    name: str
    custom_name: Optional[str] = None
    asset_type: str
    market: Optional[str] = None
    theme: Optional[str] = None

    model_config = {"from_attributes": True}


class HoldingRead(BaseModel):
    id: int
    asset: AssetRead
    amount: Decimal
    units: Optional[Decimal] = None
    cost_basis: Optional[Decimal] = None
    profit: Optional[Decimal] = None
    last_valuation_at: Optional[datetime] = None
    last_valuation_source: Optional[str] = None
    last_manual_adjustment_at: Optional[datetime] = None
    last_manual_adjustment_reason: Optional[str] = None
    last_update_type: Optional[str] = None
    manual_adjusted: bool = False

    model_config = {"from_attributes": True}


class HoldingUpdate(BaseModel):
    """Fields that can be corrected when the broker statement has changed."""

    custom_name: Optional[str] = Field(default=None, max_length=255)
    amount: Optional[Decimal] = Field(default=None, ge=0)
    units: Optional[Decimal] = Field(default=None, ge=0, decimal_places=2)
    cost_basis: Optional[Decimal] = Field(default=None, ge=0)
    profit: Optional[Decimal] = None
    correction_reason: Optional[str] = Field(default=None, max_length=500)


class TransactionCreate(BaseModel):
    asset_code: str
    asset_type: str = "fund"
    asset_name: Optional[str] = None
    operation: str = Field(pattern="^(buy|sell|dividend|transfer|adjustment|note)$")
    trade_date: date
    amount: Optional[Decimal] = Field(default=None, ge=0)
    units: Optional[Decimal] = Field(default=None, ge=0, decimal_places=2)
    price: Optional[Decimal] = Field(default=None, ge=0)
    fee: Decimal = Field(default=Decimal("0.1"), ge=0)
    reason: Optional[str] = None

    @model_validator(mode="after")
    def validate_trade_inputs(self):
        if self.operation != "note" and self.amount is None and (self.units is None or self.price is None):
            raise ValueError("请填写份额和价格")
        return self


class TransactionRead(BaseModel):
    id: int
    asset: AssetRead
    operation: str
    trade_date: date
    amount: Decimal
    units: Optional[Decimal] = None
    price: Optional[Decimal] = None
    fee: Decimal
    reason: Optional[str] = None
    created_at: datetime
    retracted_at: Optional[datetime] = None
    retraction_reason: Optional[str] = None
    retraction_effect: Optional[str] = None

    model_config = {"from_attributes": True}


class PaperTradeCreate(BaseModel):
    idempotency_key: Optional[UUID] = None
    asset_code: str = Field(min_length=1, max_length=32)
    asset_name: str = Field(min_length=1, max_length=255)
    asset_type: Literal["fund", "stock"]
    operation: Literal["buy", "sell"]
    trade_date: date
    units: Decimal = Field(gt=0, decimal_places=2)
    price: Decimal = Field(gt=0, decimal_places=6)
    fee: Decimal = Field(default=Decimal("0.1"), ge=0, decimal_places=4)
    reason: Optional[str] = Field(default=None, max_length=2000)


class PaperTradeRead(BaseModel):
    id: int
    asset_id: int
    operation: str
    trade_date: date
    amount: Decimal
    units: Decimal
    price: Decimal
    fee: Decimal
    reason: Optional[str] = None
    created_at: datetime
    retracted_at: Optional[datetime] = None
    retraction_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class PaperPortfolioPosition(BaseModel):
    id: int
    code: str
    name: str
    asset_type: str
    units: Decimal
    cost_basis: Decimal
    realized_profit: Decimal
    market_price: Optional[Decimal] = None
    market_value: Optional[Decimal] = None
    unrealized_profit: Optional[Decimal] = None
    total_profit: Optional[Decimal] = None
    quote_status: str
    quote_message: Optional[str] = None
    quote_source: Optional[str] = None
    quote_time: Optional[str] = None
    trade_count: int
    is_open: bool


class PaperQuoteRead(BaseModel):
    id: int
    captured_at: datetime
    price: Decimal
    change_pct: Optional[Decimal] = None
    quote_status: str
    quote_time: Optional[str] = None
    source: Optional[str] = None
    message: Optional[str] = None

    model_config = {"from_attributes": True}


class ImportHoldingsRequest(BaseModel):
    path: str


class ImportHoldingsResponse(BaseModel):
    imported: int
    skipped: int


class WatchlistCreate(BaseModel):
    name: str
    description: Optional[str] = None


class WatchlistItemCreate(BaseModel):
    asset_code: str
    asset_type: str = "fund"
    asset_name: Optional[str] = None


class WatchlistItemUpdate(BaseModel):
    custom_name: Optional[str] = Field(default=None, max_length=255)
    tags: Optional[list[str]] = Field(default=None, max_length=12)


class WatchlistRefreshRequest(BaseModel):
    item_ids: list[int] = Field(min_length=1, max_length=50)


class KnowledgeSearchResult(BaseModel):
    title: str
    content: str
    source_path: str
    score: int


class AgentNoteCreate(BaseModel):
    title: str
    content: str
    note_date: date
    source: str = "agent"


class ReviewAppendRequest(BaseModel):
    """Markdown generated by an external analysis agent for direct append."""

    analysis_date: date
    content: str = Field(min_length=1, max_length=200_000)
    run_id: Optional[str] = Field(default=None, max_length=120)
