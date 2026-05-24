"""
telegram_bot.py — Formatted Telegram Alert Sender

Message types:
  1. Trade alert  — full analysis breakdown with price levels
  2. Error alert  — system error notification
  3. Startup      — bot online confirmation
  4. Manual query — on-demand symbol summary
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import httpx

from config import settings

log = logging.getLogger("Telegram")

# ── Emoji maps ───────────────────────────────────────────────
_SIGNAL_EMOJI = {
    "STRONG_BUY":  "🚀",
    "BUY":         "📈",
    "NEUTRAL":     "➡️",
    "SELL":        "📉",
    "STRONG_SELL": "🔻",
}
_RISK_EMOJI = {
    "LOW":     "🟢",
    "MEDIUM":  "🟡",
    "HIGH":    "🟠",
    "EXTREME": "🔴",
}
_SENTIMENT_EMOJI = {
    "BULLISH": "📰🟢",
    "BEARISH": "📰🔴",
    "NEUTRAL": "📰⚪",
}
_CONF_EMOJI = {
    "HIGH":   "🎯",
    "MEDIUM": "🔍",
    "LOW":    "❓",
}
_ACTION_EMOJI = {
    "BUY":   "🟢 BUY",
    "SELL":  "🔴 SELL",
    "CLOSE": "🔒 CLOSE",
    "ALERT": "📌 ALERT",
    "LONG":  "🟢 LONG",
    "SHORT": "🔴 SHORT",
}


def _score_bar(score: int) -> str:
    """Visual progress bar for momentum score."""
    filled = round(score / 10)
    bar    = "█" * filled + "░" * (10 - filled)
    return f"[{bar}] {score}/100"


def _pct(val: Optional[float], prefix: bool = True) -> str:
    if val is None:
        return "n/a"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


class TelegramBot:

    def __init__(self):
        self._token   = settings.TELEGRAM_BOT_TOKEN
        self._chat    = settings.TELEGRAM_CHAT_ID
        self._alert   = settings.TELEGRAM_ALERT_CHAT_ID or settings.TELEGRAM_CHAT_ID
        self._base    = f"https://api.telegram.org/bot{self._token}"
        self._enabled = bool(self._token and self._chat and not self._token.startswith("123"))

    # ─────────────────────────────────────────────
    # PUBLIC METHODS
    # ─────────────────────────────────────────────
    async def send_trade_alert(
        self,
        alert: Any,            # TradingViewAlert
        analysis: Dict[str, Any],
    ) -> bool:
        """Main trade alert with full analysis breakdown."""
        msg = self._build_trade_message(alert, analysis)
        return await self._send(msg, chat_id=self._alert, disable_preview=True)

    async def send_analysis(self, analysis: Dict[str, Any]) -> bool:
        """Manual /analyze result."""
        msg = self._build_analysis_message(analysis)
        return await self._send(msg, chat_id=self._chat, disable_preview=True)

    async def send_startup(self) -> bool:
        mode = "📄 PAPER" if settings.PAPER_TRADING else "💵 LIVE"
        msg = (
            f"🤖 <b>AI Trading Bot Online</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Mode      : {mode}\n"
            f"Symbols   : {', '.join(settings.ALLOWED_SYMBOLS)}\n"
            f"Model     : {settings.CLAUDE_MODEL}\n"
            f"Time (UTC): {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Webhook ready at <code>/webhook/tradingview</code>"
        )
        return await self._send(msg, chat_id=self._chat)

    async def send_error(self, error: str, critical: bool = False) -> bool:
        icon = "🚨" if critical else "⚠️"
        label = "CRITICAL ERROR" if critical else "Error"
        msg = (
            f"{icon} <b>{label}</b>\n"
            f"<code>{error[:400]}</code>\n"
            f"<i>{datetime.utcnow().strftime('%H:%M:%S')} UTC</i>"
        )
        return await self._send(msg, chat_id=self._chat)

    async def send_raw(self, text: str) -> bool:
        return await self._send(text, chat_id=self._chat)

    # ─────────────────────────────────────────────
    # MESSAGE BUILDERS
    # ─────────────────────────────────────────────
    def _build_trade_message(
        self,
        alert: Any,
        a: Dict[str, Any],
    ) -> str:
        symbol   = a.get("symbol",        alert.symbol)
        action   = a.get("action",        alert.action)
        price    = a.get("current_price", alert.price or 0)
        signal   = a.get("overall_signal", "NEUTRAL")
        conf     = a.get("confidence",    "MEDIUM")
        score    = a.get("momentum_score", 50)
        risk     = a.get("risk_level",    "MEDIUM")
        news_s   = a.get("news_sentiment","NEUTRAL")
        mode     = "📄 PAPER" if settings.PAPER_TRADING else "💵 LIVE"

        # Price levels
        stop  = a.get("stop_loss")
        tp1   = a.get("take_profit_1")
        tp2   = a.get("take_profit_2")
        s_pct = a.get("stop_pct")
        t1pct = a.get("tp1_pct")
        t2pct = a.get("tp2_pct")

        # Volatility
        vol_warn = a.get("volatility_warning")
        vol_line = f"\n⚡ <b>Volatility:</b> {vol_warn}" if vol_warn else ""

        # Key factors
        factors = a.get("key_factors", [])
        fac_str = "\n".join(f"  • {f}" for f in factors[:4]) if factors else "  —"

        # Risks
        risks = a.get("risks", [])
        ris_str = "\n".join(f"  ⚠ {r}" for r in risks[:3]) if risks else "  —"

        # Recommendation
        rec = a.get("recommendation", "")

        # News summary
        news_sum = a.get("news_summary", "")

        sep = "━━━━━━━━━━━━━━━━━━━━"

        lines = [
            f"{_SIGNAL_EMOJI.get(signal,'📌')} <b>{_ACTION_EMOJI.get(action, action)}</b>  —  <b>{symbol}</b>  {mode}",
            sep,
            f"💰 Entry     : <b>${price:.4f}</b>",
            f"🛑 Stop Loss : ${stop:.4f}  ({_pct(s_pct)})" if stop else "",
            f"🎯 TP1       : ${tp1:.4f}  ({_pct(t1pct)})"  if tp1  else "",
            f"🏆 TP2       : ${tp2:.4f}  ({_pct(t2pct)})"  if tp2  else "",
            sep,
            f"📊 Momentum  : {_score_bar(score)}",
            f"{_CONF_EMOJI.get(conf,'🔍')} Confidence : {conf}",
            f"{_RISK_EMOJI.get(risk,'🟡')} Risk Level : {risk}",
            f"{_SENTIMENT_EMOJI.get(news_s,'📰⚪')} News       : {news_s}",
            vol_line,
            sep,
            "<b>Key Factors</b>",
            fac_str,
            "",
            "<b>Risks</b>",
            ris_str,
            sep,
            f"💡 <i>{rec}</i>" if rec else "",
            f"📝 <i>{news_sum}</i>" if news_sum else "",
            "",
            f"<i>Signal: {a.get('overall_signal')} | TF: {alert.timeframe or '1D'} | "
            f"{datetime.utcnow().strftime('%H:%M')} UTC</i>",
        ]

        return "\n".join(l for l in lines if l != "")

    def _build_analysis_message(self, a: Dict[str, Any]) -> str:
        symbol = a.get("symbol", "?")
        price  = a.get("current_price", 0)
        signal = a.get("overall_signal", "NEUTRAL")
        score  = a.get("momentum_score", 50)
        risk   = a.get("risk_level", "MEDIUM")
        mode   = "📄 PAPER" if settings.PAPER_TRADING else "💵 LIVE"
        reasoning = a.get("reasoning", "")

        sep = "━━━━━━━━━━━━━━━━━━━━"

        return (
            f"🔎 <b>Manual Analysis — {symbol}</b>  {mode}\n"
            f"{sep}\n"
            f"💰 Price    : <b>${price:.4f}</b>\n"
            f"{_SIGNAL_EMOJI.get(signal,'📌')} Signal  : <b>{signal}</b>\n"
            f"📊 Momentum : {_score_bar(score)}\n"
            f"{_RISK_EMOJI.get(risk,'🟡')} Risk    : {risk}\n"
            f"{sep}\n"
            f"🛑 Stop Loss: ${a.get('stop_loss', 'n/a')}\n"
            f"🎯 TP1      : ${a.get('take_profit_1', 'n/a')}\n"
            f"🏆 TP2      : ${a.get('take_profit_2', 'n/a')}\n"
            f"{sep}\n"
            f"<i>{reasoning}</i>\n"
            f"<i>{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</i>"
        )

    # ─────────────────────────────────────────────
    # HTTP SENDER
    # ─────────────────────────────────────────────
    async def _send(
        self,
        text: str,
        chat_id: str = "",
        disable_preview: bool = False,
    ) -> bool:
        if not self._enabled:
            log.warning("Telegram not configured — message suppressed.")
            log.info(f"[TELEGRAM MOCK]\n{text}")
            return False

        target = chat_id or self._chat
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.post(
                    f"{self._base}/sendMessage",
                    json={
                        "chat_id":                  target,
                        "text":                     text,
                        "parse_mode":               "HTML",
                        "disable_web_page_preview": disable_preview,
                    },
                )
            if not resp.is_success:
                log.warning(f"Telegram error {resp.status_code}: {resp.text[:200]}")
            return resp.is_success
        except Exception as e:
            log.error(f"Telegram send failed: {e}")
            return False