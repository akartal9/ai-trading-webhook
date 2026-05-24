"""
risk_manager.py — Pre-signal Risk Evaluation

Computes:
  - Signal strength from indicator context
  - ATR-based stop-loss / take-profit levels
  - Volatility flag
  - Risk tier (LOW / MEDIUM / HIGH / EXTREME)
  - Proceed / block decision based on config thresholds

This runs BEFORE Claude so Claude receives enriched context.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, Optional, Tuple

from config import settings

log = logging.getLogger("RiskManager")

# ── Leveraged ETF multipliers ────────────────────────────────
_LEVERAGE = {
    "SOXL": 3,
    "TQQQ": 3,
    "TECL": 3,
    "UPRO": 3,
    "SPXL": 3,
    "SMH":  1,
    "QQQ":  1,
    "SOXX": 1,
}


def _leverage(symbol: str) -> int:
    return _LEVERAGE.get(symbol.upper(), 1)


class RiskManager:

    def evaluate(
        self,
        symbol: str,
        action: str,
        price: float,
        indicators: Dict[str, Any],
        quote: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Returns a risk context dict that is passed to Claude and the
        Telegram formatter.
        """
        lev   = _leverage(symbol)
        notes: list[str] = []

        # ── ATR-based price levels ─────────────────────────────
        atr         = indicators.get("atr", price * settings.DEFAULT_STOP_PCT)
        atr_pct     = indicators.get("atr_pct", settings.DEFAULT_STOP_PCT * 100)
        atr_mult    = 1.5 + (lev - 1) * 0.25      # wider stop for leveraged
        stop_dist   = atr * atr_mult

        if action in ("BUY", "LONG"):
            suggested_stop = round(price - stop_dist, 4)
            suggested_tp1  = round(price + stop_dist * settings.DEFAULT_TP1_MULT, 4)
            suggested_tp2  = round(price + stop_dist * settings.DEFAULT_TP2_MULT, 4)
        elif action in ("SELL", "SHORT"):
            suggested_stop = round(price + stop_dist, 4)
            suggested_tp1  = round(price - stop_dist * settings.DEFAULT_TP1_MULT, 4)
            suggested_tp2  = round(price - stop_dist * settings.DEFAULT_TP2_MULT, 4)
        else:
            suggested_stop = round(price * (1 - settings.DEFAULT_STOP_PCT), 4)
            suggested_tp1  = round(price * (1 + settings.DEFAULT_STOP_PCT * settings.DEFAULT_TP1_MULT), 4)
            suggested_tp2  = round(price * (1 + settings.DEFAULT_STOP_PCT * settings.DEFAULT_TP2_MULT), 4)

        stop_pct = round((suggested_stop - price) / price * 100, 2)
        tp1_pct  = round((suggested_tp1  - price) / price * 100, 2)
        tp2_pct  = round((suggested_tp2  - price) / price * 100, 2)

        # ── Volatility ─────────────────────────────────────────
        daily_range_pct = indicators.get("daily_range_pct", atr_pct)
        is_volatile     = daily_range_pct > settings.VOLATILITY_THRESHOLD * 100
        if is_volatile:
            notes.append(f"High volatility: daily range {daily_range_pct:.1f}% (threshold {settings.VOLATILITY_THRESHOLD*100:.0f}%)")

        # ── RSI extremes ───────────────────────────────────────
        rsi = indicators.get("rsi")
        if rsi is not None:
            if rsi > 80:
                notes.append(f"RSI overbought: {rsi:.0f}")
            elif rsi < 25:
                notes.append(f"RSI oversold: {rsi:.0f}")

        # ── Trend alignment ────────────────────────────────────
        ema20 = indicators.get("ema20")
        ema50 = indicators.get("ema50")
        if ema20 and ema50:
            if action in ("BUY", "LONG") and price < ema20:
                notes.append("Price below EMA20 — counter-trend BUY")
            if action in ("BUY", "LONG") and ema20 < ema50:
                notes.append("EMA20 < EMA50 — short-term downtrend")

        # ── Volume ─────────────────────────────────────────────
        vol_ratio = indicators.get("volume_ratio", 1.0)
        if vol_ratio > 2.5:
            notes.append(f"Volume spike: {vol_ratio:.1f}× average")
        elif vol_ratio < 0.5:
            notes.append(f"Low volume: {vol_ratio:.1f}× average — weak conviction")

        # ── MACD ──────────────────────────────────────────────
        macd_hist = indicators.get("macd_hist")
        if macd_hist is not None:
            direction = "bullish" if macd_hist > 0 else "bearish"
            notes.append(f"MACD histogram: {macd_hist:+.4f} ({direction})")

        # ── Choppiness ────────────────────────────────────────
        chop = indicators.get("chop")
        if chop is not None and chop > 61.8:
            notes.append(f"Choppiness Index {chop:.1f} — sideways market, low trend strength")

        # ── Risk tier ─────────────────────────────────────────
        risk_level = self._risk_tier(
            atr_pct=daily_range_pct,
            leverage=lev,
            rsi=rsi,
            is_volatile=is_volatile,
            n_notes=len(notes),
        )

        # ── Signal strength ───────────────────────────────────
        signal_strength = self._signal_strength(indicators, action)

        return {
            "leverage":         lev,
            "is_leveraged":     lev > 1,
            "risk_level":       risk_level,
            "signal_strength":  signal_strength,
            "suggested_stop":   suggested_stop,
            "suggested_tp1":    suggested_tp1,
            "suggested_tp2":    suggested_tp2,
            "stop_pct":         stop_pct,
            "tp1_pct":          tp1_pct,
            "tp2_pct":          tp2_pct,
            "atr":              round(atr, 4),
            "atr_pct":          round(atr_pct, 3),
            "daily_range_pct":  round(daily_range_pct, 3),
            "is_volatile":      is_volatile,
            "volume_ratio":     round(vol_ratio, 2),
            "notes":            notes,
        }

    # ── Helpers ────────────────────────────────────────────────
    @staticmethod
    def _risk_tier(
        atr_pct: float,
        leverage: int,
        rsi: Optional[float],
        is_volatile: bool,
        n_notes: int,
    ) -> str:
        score = 0
        score += min(atr_pct / 1.0, 4)       # up to 4 pts for volatility
        score += (leverage - 1) * 1.5         # 3× ETF adds 3 pts
        if is_volatile:
            score += 2
        if rsi and (rsi > 80 or rsi < 20):
            score += 1
        score += min(n_notes * 0.5, 2)

        if score >= 8:
            return "EXTREME"
        if score >= 5:
            return "HIGH"
        if score >= 2.5:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _signal_strength(indicators: Dict[str, Any], action: str) -> str:
        score = 0
        rsi        = indicators.get("rsi")
        macd_hist  = indicators.get("macd_hist")
        vol_ratio  = indicators.get("volume_ratio", 1.0)
        p_ema20    = indicators.get("price_vs_ema20", 0)
        p_ema50    = indicators.get("price_vs_ema50", 0)

        if action in ("BUY", "LONG"):
            if rsi and 40 < rsi < 65:    score += 2
            if macd_hist and macd_hist > 0:  score += 2
            if vol_ratio > 1.5:          score += 1
            if p_ema20 > 0:              score += 1
            if p_ema50 > 0:              score += 1
        elif action in ("SELL", "SHORT"):
            if rsi and rsi > 70:         score += 2
            if macd_hist and macd_hist < 0:  score += 2
            if vol_ratio > 1.5:          score += 1
            if p_ema20 < 0:              score += 1
            if p_ema50 < 0:              score += 1

        if score >= 6:  return "STRONG"
        if score >= 4:  return "MODERATE"
        if score >= 2:  return "WEAK"
        return "NEUTRAL"