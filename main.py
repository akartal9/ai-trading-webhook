from fastapi import FastAPI, Request
from dotenv import load_dotenv
import os
import requests

load_dotenv()

app = FastAPI()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

@app.get("/")
def home():
    return {"status": "AI Trading Webhook is running"}

@app.post("/webhook/tradingview")
async def tradingview_webhook(request: Request):
    data = await request.json()

    symbol = data.get("symbol", "UNKNOWN")
    action = data.get("action", "UNKNOWN")
    price = data.get("price", "UNKNOWN")
    timeframe = data.get("timeframe", "UNKNOWN")

    message = f"""
🚨 TradingView Alert

Symbol: {symbol}
Action: {action}
Price: {price}
Timeframe: {timeframe}

Mode: Alert Only
"""

    send_telegram(message)

    return {"success": True, "received": data}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    requests.post(url, json=payload)import os
import json
import logging
from datetime import datetime

import httpx
import anthropic
from fastapi import FastAPI, Request, HTTPException

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Config from env ───────────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
PAPER_TRADING      = os.getenv("PAPER_TRADING", "true").lower() == "true"

# ── Clients ───────────────────────────────────────────────────────────────────
app            = FastAPI()
claude_client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Paper trade log (in-memory; survives the request, lost on restart) ────────
paper_trades: list[dict] = []


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def send_telegram(text: str) -> None:
    """Send a plain-text message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not set – skipping message.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            logger.error("Telegram error: %s", resp.text)


def ask_claude(symbol: str, action: str, price: float, timeframe: str) -> dict:
    """
    Call Claude and ask for a structured trade analysis.
    Returns a dict with: decision, risk_score, stop_loss, take_profit, short_reason.
    """
    prompt = f"""You are a professional trading risk analyst.

Analyse the following signal and respond with ONLY a valid JSON object — no markdown, no extra text.

Signal:
  symbol:    {symbol}
  action:    {action}
  price:     {price}
  timeframe: {timeframe}

Return exactly this JSON structure:
{{
  "decision":    "BUY | SELL | WAIT | AVOID",
  "risk_score":  <integer 1-10>,
  "stop_loss":   <float>,
  "take_profit": <float>,
  "short_reason": "<one concise sentence>"
}}"""

    message = claude_client.messages.create(
        model="claude-opus-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    logger.info("Claude raw response: %s", raw)
    return json.loads(raw)


def log_paper_trade(signal: dict, analysis: dict) -> dict:
    """Create a paper trade record and append it to the in-memory log."""
    trade = {
        "id":          len(paper_trades) + 1,
        "timestamp":   datetime.utcnow().isoformat() + "Z",
        "symbol":      signal.get("symbol"),
        "action":      signal.get("action"),
        "entry_price": signal.get("price"),
        "stop_loss":   analysis.get("stop_loss"),
        "take_profit": analysis.get("take_profit"),
        "risk_score":  analysis.get("risk_score"),
        "reason":      analysis.get("short_reason"),
        "status":      "OPEN",
    }
    paper_trades.append(trade)
    logger.info("Paper trade logged: %s", json.dumps(trade))
    return trade


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def health():
    return {"status": "ok", "paper_trading": PAPER_TRADING}


@app.get("/trades")
async def get_trades():
    """Return all paper trades logged this session."""
    return {"count": len(paper_trades), "trades": paper_trades}


@app.post("/webhook")
async def webhook(request: Request):
    # ── 1. Parse incoming signal ──────────────────────────────────────────────
    try:
        signal = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    symbol    = signal.get("symbol", "UNKNOWN")
    action    = signal.get("action", "UNKNOWN").upper()
    price     = float(signal.get("price", 0))
    timeframe = signal.get("timeframe", "N/A")

    logger.info("Webhook received: %s", signal)

    # ── 2. Forward original alert to Telegram ─────────────────────────────────
    alert_msg = (
        f"📡 <b>TradingView Signal</b>\n"
        f"Symbol: <b>{symbol}</b>\n"
        f"Action: <b>{action}</b>\n"
        f"Price:  <b>{price}</b>\n"
        f"TF:     <b>{timeframe}</b>"
    )
    await send_telegram(alert_msg)

    # ── 3. Claude AI analysis ─────────────────────────────────────────────────
    try:
        analysis = ask_claude(symbol, action, price, timeframe)
    except Exception as exc:
        logger.error("Claude analysis failed: %s", exc)
        await send_telegram(f"⚠️ Claude analysis error: {exc}")
        return {"status": "signal received", "claude": "error"}

    decision     = analysis.get("decision", "WAIT")
    risk_score   = analysis.get("risk_score", "N/A")
    stop_loss    = analysis.get("stop_loss", "N/A")
    take_profit  = analysis.get("take_profit", "N/A")
    short_reason = analysis.get("short_reason", "")

    analysis_msg = (
        f"🤖 <b>Claude Analysis</b>\n"
        f"Decision:    <b>{decision}</b>\n"
        f"Risk Score:  <b>{risk_score}/10</b>\n"
        f"Stop Loss:   <b>{stop_loss}</b>\n"
        f"Take Profit: <b>{take_profit}</b>\n"
        f"Reason: {short_reason}"
    )
    await send_telegram(analysis_msg)

    # ── 4. Paper trading ──────────────────────────────────────────────────────
    paper_trade = None
    if PAPER_TRADING and decision == "BUY":
        paper_trade = log_paper_trade(signal, analysis)
        trade_msg = (
            f"📝 <b>Paper Trade Opened</b>\n"
            f"#{paper_trade['id']} | {symbol} @ {price}\n"
            f"SL: {stop_loss} | TP: {take_profit}\n"
            f"Risk: {risk_score}/10"
        )
        await send_telegram(trade_msg)

    return {
        "status":      "ok",
        "signal":      signal,
        "analysis":    analysis,
        "paper_trade": paper_trade,
    }