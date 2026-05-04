from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- Indices ----------

class IndexQuote(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(description="Raw NSE symbol, e.g. 'NIFTY 50'")
    name: str = Field(description="Display name, e.g. 'Nifty 50'")
    last: float
    change: float
    change_pct: float
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    prev_close: float
    timestamp: datetime
    pre_open_last: Optional[float] = None
    pre_open_change_pct: Optional[float] = None


class IndicesSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    fetched_at: datetime
    sensex: IndexQuote
    nifty_50: IndexQuote
    bank_nifty: IndexQuote
    india_vix: IndexQuote

    def all(self) -> list[IndexQuote]:
        return [self.sensex, self.nifty_50, self.bank_nifty, self.india_vix]


# ---------- Movers ----------

class StockMover(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    last: float
    change_pct: float
    volume: int
    avg_volume_20d: Optional[int] = None
    volume_ratio: Optional[float] = Field(
        default=None, description="today's volume / 20-day avg"
    )


class MoversSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    fetched_at: datetime
    universe: str = "NIFTY 500"
    gainers: list[StockMover]
    losers: list[StockMover]


# ---------- FII / DII Flows ----------

class FIIDIICash(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: date
    fii_buy: float
    fii_sell: float
    fii_net: float
    dii_buy: float
    dii_sell: float
    dii_net: float


class FIIFnoNet(BaseModel):
    """FII net buy/sell across F&O segments (₹ crore, contract value)."""
    model_config = ConfigDict(frozen=True)

    date: date
    index_futures_net: Optional[float] = None
    index_options_net: Optional[float] = None
    stock_futures_net: Optional[float] = None
    stock_options_net: Optional[float] = None


class FlowsSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    fetched_at: datetime
    cash: FIIDIICash
    fno: Optional[FIIFnoNet] = None
    fno_unavailable_reason: Optional[str] = None


# ---------- Regulatory ----------

RegulatorySource = Literal["RBI", "SEBI", "NSE-IPO"]


class RegulatoryItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: RegulatorySource
    title: str
    url: str
    published: datetime
    summary: Optional[str] = None


class RegulatorySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    fetched_at: datetime
    items: list[RegulatoryItem]
    unavailable_sources: list[str] = Field(default_factory=list)


# ---------- Macro ----------

class MacroQuote(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    last: float
    prev_close: float
    change: float
    change_pct: float
    as_of: datetime


class MacroSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    fetched_at: datetime
    usdinr: MacroQuote
    dxy: MacroQuote
    brent: MacroQuote
    gold: MacroQuote
    india_gsec_10y: MacroQuote

    def all(self) -> list[MacroQuote]:
        return [self.usdinr, self.dxy, self.brent, self.gold, self.india_gsec_10y]


# ---------- Briefing ----------

class PulseBriefing(BaseModel):
    """Top-level immutable snapshot consumed by the formatter."""
    model_config = ConfigDict(frozen=True)

    fetched_at: datetime
    indices: IndicesSnapshot
    movers: MoversSnapshot
    flows: FlowsSnapshot
    regulatory: RegulatorySnapshot
    macro: MacroSnapshot
