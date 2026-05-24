"""
config.py — Environment-based configuration (Pydantic Settings v2)

All values are read from environment variables or the .env file.
Nothing is hard-coded here; see .env.example for the full list.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ─────────────────────────────────────────────
    PORT: int = Field(default=8000)
    DEBUG: bool = Field(default=False)
    WEBHOOK_SECRET: str = Field(default="")   # TradingView secret header
    LOG_LEVEL: str = Field(default="INFO")

    # ── Symbols ─────────────────────────────────────────────────
    ALLOWED_SYMBOLS: List[str] = Field(
        default=["SOXL", "TQQQ", "QQQ", "SOXX", "NVDA"]
    )

    # ── Anthropic / Claude ───────────────────────────────────────
    ANTHROPIC_API_KEY: str = Field(default="")
    CLAUDE_MODEL: str = Field(default="claude-opus-4-6")
    CLAUDE_MAX_TOKENS: int = Field(default=1500)
    CLAUDE_TEMPERATURE: float = Field(default=0.2)

    # ── Telegram ─────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = Field(default="")
    TELEGRAM_CHAT_ID: str = Field(default="")
    TELEGRAM_ALERT_CHAT_ID: str = Field(default="")   # Optional separate channel for alerts

    # ── viaNexus ─────────────────────────────────────────────────
    VIANEXUS_API_KEY: str = Field(default="")
    VIANEXUS_BASE_URL: str = Field(default="https://api.vianexus.com/v1")
    VIANEXUS_TIMEOUT: int = Field(default=10)

    # ── Risk Management ──────────────────────────────────────────
    MAX_POSITION_PCT: float = Field(default=0.10)     # 10% of portfolio per position
    MAX_DAILY_LOSS_PCT: float = Field(default=0.02)   # 2% max daily loss
    DEFAULT_STOP_PCT: float = Field(default=0.05)     # 5% default stop loss
    DEFAULT_TP1_MULT: float = Field(default=1.5)      # TP1 = risk × 1.5
    DEFAULT_TP2_MULT: float = Field(default=3.0)      # TP2 = risk × 3.0
    VOLATILITY_THRESHOLD: float = Field(default=0.04) # 4% daily range = volatile
    MIN_MOMENTUM_SCORE: int = Field(default=40)       # Skip signals below this
    PAPER_TRADING: bool = Field(default=True)

    # ── Cache ────────────────────────────────────────────────────
    QUOTE_CACHE_TTL: int = Field(default=30)    # seconds
    NEWS_CACHE_TTL: int = Field(default=300)    # 5 minutes


settings = Settings()