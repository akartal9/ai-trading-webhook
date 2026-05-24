"""
models.py — Pydantic v2 data models

All request / response schemas used across the system.
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


# ─────────────────────────────────────────────
# TradingView Webhook Payload
# ─────────────────────────────────────────────
class TradingViewAlert(BaseModel):
    """
    Expected JSON body from TradingView webhook.

    Minimal TradingView alert message template:
    {
      "symbol": "{{ticker}}",
      "action": "{{strategy.order.action}}",
      "price": {{close}},
      "volume": {{volume}},
      "indicators": {
        "rsi": {{plot_0}},
        "ema20": {{plot_1}},
        "ema50": {{plot_2}},
        "atr": {{plot_3}},
        "macd": {{plot_4}},
        "signal": {{plot_5}}
      },
      "timeframe": "{{interval}}",
      "strategy": "{{strategy.order.comment}}"
    }
    """
    symbol: str
    action: str                                   # BUY / SELL / CLOSE / ALERT
    price: Optional[float] = None
    volume: Optional[float] = None
    timeframe: Optional[str] = "1D"
    strategy: Optional[str] = None
    indicators: Optional[Dict[str, float]] = Field(default_factory=dict)
    timestamp: Optional[str] = None              # ISO string from TV
    extra: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalise_symbol(cls, v: str) -> str:
        return v.upper().strip().replace("NASDAQ:", "").replace("NYSE:", "")

    @field_validator("action", mode="before")
    @classmethod
    def normalise_action(cls, v: str) -> str:
        return v.upper().strip()


# ─────────────────────────────────────────────
# Market Data
# ─────────────────────────────────────────────
class QuoteData(BaseModel):
    symbol: str
    price: float
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    change_pct: Optional[float] = None
    market_cap: Optional[float] = None
    avg_volume: Optional[float] = None
    timestamp: Optional[str] = None


class NewsItem(BaseModel):
    title: str
    summary: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    published_at: Optional[str] = None
    sentiment_score: Optional[float] = None      # -1.0 to +1.0
    sentiment_label: Optional[str] = None        # BULLISH / BEARISH / NEUTRAL


# ─────────────────────────────────────────────
# Risk Evaluation
# ─────────────────────────────────────────────
class RiskAssessment(BaseModel):
    symbol: str
    action: str
    signal_strength: str = "NEUTRAL"             # STRONG / MODERATE / WEAK / NEUTRAL
    risk_level: str = "MEDIUM"                   # LOW / MEDIUM / HIGH / EXTREME
    proceed: bool = True
    notes: List[str] = Field(default_factory=list)

    # Computed price levels
    current_price: float = 0.0
    suggested_stop: Optional[float] = None
    suggested_tp1: Optional[float] = None
    suggested_tp2: Optional[float] = None
    stop_pct: Optional[float] = None
    tp1_pct: Optional[float] = None
    tp2_pct: Optional[float] = None

    # Volatility
    atr: Optional[float] = None
    daily_range_pct: Optional[float] = None
    is_volatile: bool = False


# ─────────────────────────────────────────────
# Claude Analysis Result
# ─────────────────────────────────────────────
class AnalysisResult(BaseModel):
    symbol: str
    action: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    # Core scores
    momentum_score: int = Field(default=50, ge=0, le=100)
    confidence: str = "MEDIUM"                   # HIGH / MEDIUM / LOW
    overall_signal: str = "NEUTRAL"              # STRONG_BUY / BUY / NEUTRAL / SELL / STRONG_SELL

    # Price levels
    current_price: float = 0.0
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    stop_pct: Optional[float] = None
    tp1_pct: Optional[float] = None
    tp2_pct: Optional[float] = None

    # Sentiment
    news_sentiment: str = "NEUTRAL"              # BULLISH / BEARISH / NEUTRAL
    sentiment_score: float = 0.0                 # -1.0 to +1.0
    news_summary: Optional[str] = None

    # Risk / Volatility
    risk_level: str = "MEDIUM"
    volatility_warning: Optional[str] = None
    is_volatile: bool = False

    # Analysis text
    reasoning: Optional[str] = None
    key_factors: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    recommendation: Optional[str] = None

    # Meta
    paper_trading: bool = True
    model_used: Optional[str] = None


# ─────────────────────────────────────────────
# API Responses
# ─────────────────────────────────────────────
class WebhookResponse(BaseModel):
    status: str
    symbol: str
    message: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    paper_trading: bool = True
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())