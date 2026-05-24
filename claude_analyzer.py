"""
claude_analyzer.py — Claude AI Analysis Engine

Sends enriched market context to Claude and receives a structured
JSON analysis containing:
  - momentum_score       (0–100)
  - overall_signal       (STRONG_BUY / BUY / NEUTRAL / SELL / STRONG_SELL)
  - confidence           (HIGH / MEDIUM / LOW)
  - stop_loss / tp1 / tp2 price levels
  - news_sentiment       (BULLISH / BEARISH / NEUTRAL)
  - volatility_warning   (string or null)
  - risk_level           (LOW / MEDIUM / HIGH / EXTREME)
  - key_factors          (list of strings)
  - risks                (list of strings)
  - reasoning            (short paragraph)
  - recommendation       (one-sentence action)
"""

from __future__ import annotations
import json
import logging
import re
from typing import Any, Dict, List, Optional

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings

log = logging.getLogger("ClaudeAnalyzer")

_client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

# ─────────────────────────────────────────────
# PROMPT BUILDER
# ─────────────────────────────────────────────
_SYSTEM_PROMPT = """You are an expert quantitative trading analyst specialising in leveraged ETFs,
specifically SOXL (3× semiconductor), TQQQ (3× Nasdaq-100), SMH (semiconductor ETF) and QQQ (Nasdaq-100).

Your job is to evaluate inbound TradingView alerts enriched with live market data and return a
precise, structured JSON analysis. You must be data-driven, concise, and never speculative.

IMPORTANT RULES:
1. Always return ONLY valid JSON — no markdown fences, no extra commentary.
2. For leveraged ETFs (SOXL, TQQQ): tighten stops and reduce risk ratings by one tier vs. unleveraged.
3. Momentum score: 0 = extreme sell, 50 = neutral, 100 = extreme buy.
4. Stop loss must ALWAYS be set — default to ATR×2 below entry when not obvious.
5. TP1 = stop_distance × 1.5 above entry; TP2 = stop_distance × 3.0 above entry (for BUY).
6. If volatility is HIGH/EXTREME, set volatility_warning to a concise string; otherwise null.
7. This system is for educational/paper trading analysis only. State that in recommendation.

OUTPUT SCHEMA (return exactly this shape):
{
  "momentum_score": <int 0-100>,
  "overall_signal": "<STRONG_BUY|BUY|NEUTRAL|SELL|STRONG_SELL>",
  "confidence": "<HIGH|MEDIUM|LOW>",
  "stop_loss": <float>,
  "take_profit_1": <float>,
  "take_profit_2": <float>,
  "stop_pct": <float>,
  "tp1_pct": <float>,
  "tp2_pct": <float>,
  "news_sentiment": "<BULLISH|BEARISH|NEUTRAL>",
  "sentiment_score": <float -1.0 to 1.0>,
  "news_summary": "<one sentence>",
  "risk_level": "<LOW|MEDIUM|HIGH|EXTREME>",
  "volatility_warning": <string or null>,
  "key_factors": ["<factor1>", "<factor2>", "<factor3>"],
  "risks": ["<risk1>", "<risk2>"],
  "reasoning": "<2–3 sentence analysis>",
  "recommendation": "<one-sentence action for paper trading>"
}"""


def _build_user_prompt(
    symbol: str,
    action: str,
    price: float,
    quote: Dict[str, Any],
    indicators: Dict[str, Any],
    news: List[Dict[str, Any]],
    risk_context: Dict[str, Any],
    timeframe: str = "1D",
    strategy: Optional[str] = None,
) -> str:

    ind_block = "\n".join(
        f"  {k}: {v}" for k, v in indicators.items()
    ) if indicators else "  (none provided)"

    news_block = "\n".join(
        f"  [{i+1}] {n.get('title','')[:120]} — {n.get('source','')}"
        for i, n in enumerate(news[:6])
    ) if news else "  (no recent news)"

    risk_block = "\n".join(
        f"  {k}: {v}" for k, v in risk_context.items()
    ) if risk_context else "  (none)"

    tv_extra = ""
    if strategy:
        tv_extra = f"\nStrategy/comment: {strategy}"

    return f"""=== TRADINGVIEW ALERT ===
Symbol    : {symbol}
Action    : {action}
Price     : ${price:.4f}
Timeframe : {timeframe}{tv_extra}

=== LIVE QUOTE ===
  Open        : ${quote.get('open', 'n/a')}
  High        : ${quote.get('high', 'n/a')}
  Low         : ${quote.get('low', 'n/a')}
  Close       : ${quote.get('close', 'n/a')}
  Volume      : {quote.get('volume', 'n/a'):,} (if int)
  Change %    : {quote.get('change_pct', 0):+.2f}%

=== TECHNICAL INDICATORS ===
{ind_block}

=== RECENT NEWS ===
{news_block}

=== RISK CONTEXT ===
{risk_block}

Analyse this alert and return the JSON schema exactly as specified in the system prompt."""


# ─────────────────────────────────────────────
# ANALYZER
# ─────────────────────────────────────────────
class ClaudeAnalyzer:

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def analyze(
        self,
        symbol: str,
        action: str,
        price: float,
        quote: Dict[str, Any],
        news: List[Dict[str, Any]],
        indicators: Dict[str, Any],
        risk_context: Optional[Dict[str, Any]] = None,
        timeframe: str = "1D",
        strategy: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Call Claude and return the structured analysis dict.
        Falls back to a safe default if parsing fails.
        """
        prompt = _build_user_prompt(
            symbol=symbol,
            action=action,
            price=price,
            quote=quote,
            indicators=indicators,
            news=news,
            risk_context=risk_context or {},
            timeframe=timeframe,
            strategy=strategy,
        )

        log.info(f"Sending {symbol} {action} @ ${price:.2f} to Claude…")

        try:
            response = _client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=settings.CLAUDE_MAX_TOKENS,
                temperature=settings.CLAUDE_TEMPERATURE,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()

            # Strip markdown fences if Claude adds them anyway
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$",          "", raw).strip()

            analysis = json.loads(raw)
            analysis["symbol"]       = symbol
            analysis["action"]       = action
            analysis["current_price"] = price
            analysis["model_used"]   = settings.CLAUDE_MODEL
            analysis["paper_trading"] = settings.PAPER_TRADING

            log.info(
                f"Analysis: {symbol} score={analysis.get('momentum_score')} "
                f"signal={analysis.get('overall_signal')} "
                f"risk={analysis.get('risk_level')}"
            )
            return analysis

        except json.JSONDecodeError as e:
            log.error(f"Claude JSON parse error: {e} | raw={raw[:300]}")
            return self._fallback(symbol, action, price)
        except Exception as e:
            log.error(f"Claude API error: {e}")
            return self._fallback(symbol, action, price)

    @staticmethod
    def _fallback(symbol: str, action: str, price: float) -> Dict[str, Any]:
        """Return a neutral, safe default when Claude is unreachable."""
        stop  = round(price * 0.95, 4)
        tp1   = round(price * 1.075, 4)
        tp2   = round(price * 1.15,  4)
        return {
            "symbol":            symbol,
            "action":            action,
            "current_price":     price,
            "momentum_score":    50,
            "overall_signal":    "NEUTRAL",
            "confidence":        "LOW",
            "stop_loss":         stop,
            "take_profit_1":     tp1,
            "take_profit_2":     tp2,
            "stop_pct":          -5.0,
            "tp1_pct":           7.5,
            "tp2_pct":           15.0,
            "news_sentiment":    "NEUTRAL",
            "sentiment_score":   0.0,
            "news_summary":      "Analysis unavailable — Claude API error.",
            "risk_level":        "HIGH",
            "volatility_warning": "Analysis failed; treat all levels as estimates.",
            "key_factors":       ["Claude API unavailable"],
            "risks":             ["Unable to complete AI analysis"],
            "reasoning":         "Fallback values used due to API error.",
            "recommendation":    "Do not trade — analysis incomplete.",
            "paper_trading":     settings.PAPER_TRADING,
            "model_used":        "fallback",
        }