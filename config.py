"""config.py — Environment variable loader & app-wide constants."""

import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()  # reads .env file automatically
except ImportError:
    pass

# ── Nansen ────────────────────────────────────────────────
NANSEN_API_KEY: str = os.environ.get("NANSEN_API_KEY", "")

# ── Telegram ───────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID:   str = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Discord ────────────────────────────────────────────────
DISCORD_WEBHOOK_URL: str = os.environ.get("DISCORD_WEBHOOK_URL", "")

# ── Chains ──────────────────────────────────────────────────
CHAINS: list[str] = [
    "ethereum",
    "solana",
    "arbitrum",
    "base",
    "bitcoin",
    "bsc",
    "polygon",
    "optimism",
    "avalanche",
    "linea"
]

# ── VIP Tracked Wallets (Stalking) ──────────────────────────
# Users can add any wallet address here to shadow them 24/7
TRACKED_WALLETS: dict[str, str] = {
    "Vitalik Buterin": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    "Justin Sun": "0x3DdfA8eC3052539b6C9549F12cEA2C295cfF5296"
}
VIP_TX_USD_MIN: float = 10_000   # Minimum $10k transfer to trigger VIP alert

# ── Polling ────────────────────────────────────────────────
POLL_INTERVAL_MIN: int = 30        # schedule interval
NANSEN_TIMEOUT_SEC: int = 25       # subprocess timeout
NANSEN_RETRY: int = 2              # retries on parse failure
RATE_LIMIT_SLEEP: float = 1.0      # seconds between API calls

# ── Alert thresholds ───────────────────────────────────────
STRONG_FLOW_USD:       float = 500_000   # |net_flow_usd| >= this
MIN_SM_WALLETS:        int   = 3         # smart_money_count >= this
WHALE_TRADE_USD:       float = 250_000   # single dex trade >= this

# ── Dedup window ───────────────────────────────────────────
ALERT_COOLDOWN_HOURS: int = 2

# ── Log file ───────────────────────────────────────────────
ALERTS_LOG_FILE: str = "alerts_log.json"

# ── Validation ─────────────────────────────────────────────
def validate():
    missing = []
    if not NANSEN_API_KEY:
        missing.append("NANSEN_API_KEY")
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_ID:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        print(f"❌  Missing environment variables: {', '.join(missing)}")
        print("    Set them and re-run. See README.md for instructions.")
        sys.exit(1)
