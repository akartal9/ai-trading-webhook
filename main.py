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
    requests.post(url, json=payload)