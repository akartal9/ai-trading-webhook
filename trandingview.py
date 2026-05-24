{
  "_readme": "Paste these JSON bodies into TradingView Alert → Message tab. Set Webhook URL to https://your-app.railway.app/webhook/tradingview and add header X-Webhook-Secret: <your_secret>",

  "examples": [

    {
      "_label": "TQQQ — BUY signal with full indicators",
      "symbol": "TQQQ",
      "action": "BUY",
      "price": "{{close}}",
      "volume": "{{volume}}",
      "timeframe": "{{interval}}",
      "strategy": "EMA Crossover + RSI",
      "indicators": {
        "rsi":    "{{plot_0}}",
        "ema20":  "{{plot_1}}",
        "ema50":  "{{plot_2}}",
        "atr":    "{{plot_3}}",
        "macd":   "{{plot_4}}",
        "signal": "{{plot_5}}"
      }
    },

    {
      "_label": "SOXL — SELL / exit signal",
      "symbol": "SOXL",
      "action": "SELL",
      "price": "{{close}}",
      "volume": "{{volume}}",
      "timeframe": "{{interval}}",
      "strategy": "Overbought RSI exit",
      "indicators": {
        "rsi":   "{{plot_0}}",
        "ema20": "{{plot_1}}",
        "ema50": "{{plot_2}}",
        "atr":   "{{plot_3}}"
      }
    },

    {
      "_label": "QQQ — Simple BUY alert (minimal payload)",
      "symbol": "QQQ",
      "action": "BUY",
      "price": "{{close}}",
      "timeframe": "1D"
    },

    {
      "_label": "SMH — ALERT (informational, no trade action)",
      "symbol": "SMH",
      "action": "ALERT",
      "price": "{{close}}",
      "timeframe": "4h",
      "strategy": "Support level reached",
      "indicators": {
        "rsi":  "{{plot_0}}",
        "atr":  "{{plot_1}}"
      }
    },

    {
      "_label": "TQQQ — CLOSE position signal",
      "symbol": "TQQQ",
      "action": "CLOSE",
      "price": "{{close}}",
      "timeframe": "{{interval}}",
      "strategy": "Trailing stop hit"
    },

    {
      "_label": "Static test payload (for curl / Postman testing)",
      "symbol": "SOXL",
      "action": "BUY",
      "price": 32.50,
      "volume": 5820000,
      "timeframe": "1D",
      "strategy": "RSI Oversold Bounce",
      "indicators": {
        "rsi":    28.4,
        "ema20":  33.12,
        "ema50":  35.77,
        "atr":    1.84,
        "macd":  -0.42,
        "signal": -0.38
      }
    }

  ],

  "tradingview_pine_template": "// ── Paste in Pine Script alert() call ──\nalert(\n  '{\"symbol\": \"' + syminfo.ticker + '\", ' +\n  '\"action\": \"BUY\", ' +\n  '\"price\": ' + str.tostring(close) + ', ' +\n  '\"volume\": ' + str.tostring(volume) + ', ' +\n  '\"timeframe\": \"' + timeframe.period + '\", ' +\n  '\"indicators\": {' +\n    '\"rsi\": '   + str.tostring(rsi_val,   \"#.##\") + ', ' +\n    '\"ema20\": \" + str.tostring(ema20_val, \"#.####\") + ', ' +\n    '\"atr\": '   + str.tostring(atr_val,   \"#.####\") +\n  '}}',\n  alert.freq_once_per_bar_close\n)",

  "curl_test": "curl -X POST https://your-app.railway.app/webhook/tradingview \\\n  -H 'Content-Type: application/json' \\\n  -H 'X-Webhook-Secret: your_secret_token_here' \\\n  -d '{\"symbol\":\"TQQQ\",\"action\":\"BUY\",\"price\":52.30,\"timeframe\":\"1D\",\"strategy\":\"Test\"}'"
}