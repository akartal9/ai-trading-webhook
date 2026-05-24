"""
market_data.py — Market data fetcher using yfinance

Provides:
  - Real-time quote (price, volume, change %)
  - OHLCV history (30 days, 1-day bars)
  - Technical indicators: ATR, RSI, EMA20/50, MACD, Bollinger Bands
  - Basic news headlines via yfinance .news

All results are cached to avoid hammering Yahoo Finance.
"""

from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf
from cachetools import TTLCache

from config import settings

log = logging.getLogger("MarketData")

# ── In-memory cache ──────────────────────────────────────────
_quote_cache: TTLCache = TTLCache(maxsize=50, ttl=settings.QUOTE_CACHE_TTL)
_news_cache:  TTLCache = TTLCache(maxsize=50, ttl=settings.NEWS_CACHE_TTL)
_hist_cache:  TTLCache = TTLCache(maxsize=20, ttl=120)   # 2-minute hist cache


# ─────────────────────────────────────────────
# HELPERS — Technical Indicators
# ─────────────────────────────────────────────
def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, prev_close = df["High"], df["Low"], df["Close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _macd(series: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast  = _ema(series, 12)
    slow  = _ema(series, 26)
    macd  = fast - slow
    sig   = _ema(macd, 9)
    hist  = macd - sig
    return macd, sig, hist


def _bollinger(series: pd.Series, period: int = 20) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid   = series.rolling(period).mean()
    std   = series.rolling(period).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    return upper, mid, lower


def _chop(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Choppiness Index — high = choppy, low = trending."""
    atr_sum = _atr(df, 1).rolling(period).sum()
    hi      = df["High"].rolling(period).max()
    lo      = df["Low"].rolling(period).min()
    chop    = 100 * np.log10(atr_sum / (hi - lo).replace(0, np.nan)) / np.log10(period)
    return chop


def compute_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """Return a flat dict of the latest indicator values."""
    if df is None or len(df) < 30:
        return {}

    close = df["Close"]
    last  = close.iloc[-1]

    rsi_s  = _rsi(close)
    atr_s  = _atr(df)
    ema20  = _ema(close, 20)
    ema50  = _ema(close, 50)
    macd_l, sig_l, hist_l = _macd(close)
    bb_up, bb_mid, bb_lo  = _bollinger(close)
    chop_s = _chop(df)

    # Volume ratio vs 20-day avg
    vol_avg   = df["Volume"].rolling(20).mean().iloc[-1]
    vol_ratio = df["Volume"].iloc[-1] / vol_avg if vol_avg else 1.0

    # Daily range %
    daily_range_pct = (df["High"].iloc[-1] - df["Low"].iloc[-1]) / last * 100

    return {
        "rsi":             round(float(rsi_s.iloc[-1]),  2),
        "ema20":           round(float(ema20.iloc[-1]),  4),
        "ema50":           round(float(ema50.iloc[-1]),  4),
        "atr":             round(float(atr_s.iloc[-1]),  4),
        "atr_pct":         round(float(atr_s.iloc[-1]) / last * 100, 3),
        "macd":            round(float(macd_l.iloc[-1]), 4),
        "macd_signal":     round(float(sig_l.iloc[-1]),  4),
        "macd_hist":       round(float(hist_l.iloc[-1]), 4),
        "bb_upper":        round(float(bb_up.iloc[-1]),  4),
        "bb_mid":          round(float(bb_mid.iloc[-1]), 4),
        "bb_lower":        round(float(bb_lo.iloc[-1]),  4),
        "chop":            round(float(chop_s.iloc[-1]), 2),
        "volume_ratio":    round(float(vol_ratio),       2),
        "daily_range_pct": round(float(daily_range_pct), 3),
        "price_vs_ema20":  round((last - float(ema20.iloc[-1])) / float(ema20.iloc[-1]) * 100, 2),
        "price_vs_ema50":  round((last - float(ema50.iloc[-1])) / float(ema50.iloc[-1]) * 100, 2),
    }


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────
class MarketDataClient:

    # ── Quote ──────────────────────────────────────────────────
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        if symbol in _quote_cache:
            return _quote_cache[symbol]

        result = await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_quote, symbol
        )
        _quote_cache[symbol] = result
        return result

    def _fetch_quote(self, symbol: str) -> Dict[str, Any]:
        try:
            tk = yf.Ticker(symbol)
            info = tk.fast_info
            hist = tk.history(period="2d", interval="1d")

            price      = float(getattr(info, "last_price",        0) or 0)
            prev_close = float(getattr(info, "previous_close",    0) or 0)
            change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0

            row = hist.iloc[-1] if not hist.empty else {}
            return {
                "symbol":      symbol,
                "price":       round(price, 4),
                "open":        round(float(row.get("Open",  price)), 4),
                "high":        round(float(row.get("High",  price)), 4),
                "low":         round(float(row.get("Low",   price)), 4),
                "close":       round(float(row.get("Close", price)), 4),
                "volume":      int(row.get("Volume", 0)),
                "change_pct":  round(change_pct, 3),
                "market_cap":  getattr(info, "market_cap", None),
                "timestamp":   datetime.utcnow().isoformat(),
            }
        except Exception as e:
            log.warning(f"Quote fetch failed for {symbol}: {e}")
            return {"symbol": symbol, "price": 0.0}

    # ── Historical OHLCV + indicators ──────────────────────────
    async def get_historical(self, symbol: str, days: int = 60) -> Dict[str, Any]:
        cache_key = f"{symbol}_{days}"
        if cache_key in _hist_cache:
            return _hist_cache[cache_key]

        result = await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_historical, symbol, days
        )
        _hist_cache[cache_key] = result
        return result

    def _fetch_historical(self, symbol: str, days: int) -> Dict[str, Any]:
        try:
            tk   = yf.Ticker(symbol)
            df   = tk.history(period=f"{days}d", interval="1d")
            if df.empty:
                return {"symbol": symbol, "indicators": {}}

            df.index = pd.to_datetime(df.index)
            indicators = compute_indicators(df)

            recent = df.tail(5)[["Open","High","Low","Close","Volume"]].round(4)
            return {
                "symbol":     symbol,
                "bars":       recent.to_dict(orient="records"),
                "indicators": indicators,
            }
        except Exception as e:
            log.warning(f"Historical fetch failed for {symbol}: {e}")
            return {"symbol": symbol, "indicators": {}}

    # ── News ───────────────────────────────────────────────────
    async def get_news(self, symbol: str, limit: int = 8) -> List[Dict[str, Any]]:
        if symbol in _news_cache:
            return _news_cache[symbol][:limit]

        result = await asyncio.get_event_loop().run_in_executor(
            None, self._fetch_news, symbol, limit
        )
        _news_cache[symbol] = result
        return result

    def _fetch_news(self, symbol: str, limit: int) -> List[Dict[str, Any]]:
        try:
            tk    = yf.Ticker(symbol)
            items = tk.news or []
            news  = []
            for n in items[:limit]:
                content = n.get("content", {})
                title   = (
                    content.get("title")
                    or n.get("title", "")
                )
                summary = (
                    content.get("summary")
                    or content.get("description")
                    or ""
                )
                source_info = content.get("provider", {}) or {}
                source = (
                    source_info.get("displayName")
                    or n.get("source", "")
                )
                pub = (
                    content.get("pubDate")
                    or content.get("displayTime")
                    or ""
                )
                url = ""
                for link_obj in (content.get("clickThroughUrl") or []):
                    url = link_obj.get("url", "") if isinstance(link_obj, dict) else str(link_obj)
                    break

                if title:
                    news.append({
                        "title":        title,
                        "summary":      summary[:300] if summary else "",
                        "source":       source,
                        "published_at": pub,
                        "url":          url,
                    })
            return news
        except Exception as e:
            log.warning(f"News fetch failed for {symbol}: {e}")
            return []