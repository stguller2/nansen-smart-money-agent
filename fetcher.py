"""fetcher.py — Nansen CLI subprocess wrapper.

All CLI calls go through `run_nansen()`. Returns parsed JSON dict.
API call counter is exposed as `total_calls` for eligibility reporting.
"""

import json
import os
import subprocess
import time
from typing import Any

import config

total_calls: int = 0   # module-level counter


# ── internal runner ────────────────────────────────────────

def run_nansen(subcommand: str, extra_flags: str = "", demo_data: dict | None = None) -> dict[str, Any]:
    """Execute a Nansen CLI command, return parsed JSON or error dict."""
    global total_calls

    if demo_data is not None:            # demo / test mode shortcut
        total_calls += 1
        return demo_data

    env = os.environ.copy()
    env["NANSEN_API_KEY"] = config.NANSEN_API_KEY

    cmd = f"nansen research {subcommand} {extra_flags} --output json".strip()

    for attempt in range(1, config.NANSEN_RETRY + 1):
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=config.NANSEN_TIMEOUT_SEC,
                env=env,
            )
            time.sleep(config.RATE_LIMIT_SLEEP)
            data = json.loads(result.stdout)

            # Detect credit exhaustion
            if data.get("code") == "CREDITS_EXHAUSTED":
                print(f"  ❌  Credits exhausted on: {subcommand}")
                return {"error": "CREDITS_EXHAUSTED", "data": {"data": []}}

            total_calls += 1
            return data

        except json.JSONDecodeError:
            err = result.stderr[:120] if result.stderr else result.stdout[:120]
            print(f"  ⚠️  JSON error (attempt {attempt}): {err}")
            if attempt < config.NANSEN_RETRY:
                time.sleep(2 ** attempt)
            else:
                return {"error": err, "data": {"data": []}}

        except subprocess.TimeoutExpired:
            print(f"  ⏰  Timeout (attempt {attempt}): {subcommand}")
            if attempt < config.NANSEN_RETRY:
                time.sleep(2 ** attempt)
            else:
                return {"error": "timeout", "data": {"data": []}}

    return {"error": "unexpected", "data": {"data": []}}


def _list(response: dict) -> list:
    """Safely extract the data list from a Nansen response."""
    inner = response.get("data", response)
    if isinstance(inner, dict):
        inner = inner.get("data", [])
    return inner if isinstance(inner, list) else []


# ── public fetch functions ─────────────────────────────────

def fetch_netflow(chain: str, demo=False) -> list:
    """Smart Money net flows for a specific chain, 1h window."""
    key = f"netflow_{chain[:3]}"
    data = run_nansen(
        "smart-money netflow",
        f"--chain {chain} --timeframe 1h --limit 20",
        demo_data=_DEMO.get(key, {"data": {"data": []}}) if demo else None,
    )
    return _list(data)


def fetch_dex_trades(chain: str, demo=False) -> list:
    """Smart Money DEX trades for a specific chain, 1h window."""
    key = f"dex_{chain[:3]}"
    data = run_nansen(
        "smart-money dex-trades",
        f"--chain {chain} --timeframe 1h --limit 10",
        demo_data=_DEMO.get(key, {"data": {"data": []}}) if demo else None,
    )
    return _list(data)


def fetch_token_screener(chain: str, demo=False) -> list:
    """Token screener for a specific chain, 1h timeframe."""
    key = f"screener_{chain[:3]}"
    data = run_nansen(
        "token screener",
        f"--chain {chain} --timeframe 1h --limit 10",
        demo_data=_DEMO.get(key, {"data": {"data": []}}) if demo else None,
    )
    return _list(data)


def fetch_wallet_transactions(address: str, demo=False) -> list:
    """Fetch recent transactions / transfers for a specific tracked VIP wallet."""
    data = run_nansen(
        "research profiler transactions",
        f"--address {address} --limit 10",
        demo_data=_DEMO.get(f"vip_{address[-4:]}") if demo else None,
    )
    return _list(data)


# ── demo / test data ───────────────────────────────────────

_DEMO: dict[str, dict] = {
    "vip_6045": {  # Vitalik mock
        "success": True,
        "data": {"data": [
            {
                "transaction_hash": "0x1a2b3c4d5e...",
                "block_timestamp": "2026-03-24T22:30:00",
                "from_address": "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
                "to_address": "0xpool...",
                "token_symbol": "ETH",
                "value_usd": 150_000.0,
            }
        ]}
    },
    "vip_5296": {  # Justin Sun mock
        "success": True,
        "data": {"data": [
            {
                "transaction_hash": "0x9f8e7d6c5b...",
                "block_timestamp": "2026-03-24T22:31:00",
                "to_address": "0x3ddfa8ec3052539b6c9549f12cea2c295cff5296",
                "from_address": "0xbinance...",
                "token_symbol": "USDT",
                "value_usd": 2_500_000.0,
            }
        ]}
    },
    "netflow_eth": {
        "success": True,
        "data": {"data": [
            {"token_symbol": "WBTC",  "chain": "ethereum", "net_flow_usd":  820_000, "inflow_usd":  1_100_000, "outflow_usd":  280_000, "smart_money_count": 5,  "price_usd": 64_200.0,  "price_change_pct": 2.1},
            {"token_symbol": "PEPE",  "chain": "ethereum", "net_flow_usd": -610_000, "inflow_usd":    90_000, "outflow_usd":  700_000, "smart_money_count": 4,  "price_usd": 0.0000085, "price_change_pct": -5.3},
            {"token_symbol": "LINK",  "chain": "ethereum", "net_flow_usd":  210_000, "inflow_usd":   310_000, "outflow_usd":  100_000, "smart_money_count": 2,  "price_usd": 14.20,     "price_change_pct": 1.4},
            {"token_symbol": "ARB",   "chain": "ethereum", "net_flow_usd": -120_000, "inflow_usd":    50_000, "outflow_usd":  170_000, "smart_money_count": 1,  "price_usd": 0.78,      "price_change_pct": -0.6},
        ]}
    },
    "netflow_sol": {
        "success": True,
        "data": {"data": [
            {"token_symbol": "JTO",   "chain": "solana",   "net_flow_usd":  530_000, "inflow_usd":   680_000, "outflow_usd":  150_000, "smart_money_count": 6,  "price_usd": 2.34,  "price_change_pct": 3.7},
            {"token_symbol": "JUP",   "chain": "solana",   "net_flow_usd": -90_000,  "inflow_usd":    60_000, "outflow_usd":  150_000, "smart_money_count": 2,  "price_usd": 0.55,  "price_change_pct": -1.2},
        ]}
    },
    "dex_eth": {
        "success": True,
        "data": {"data": [
            {"token_bought_symbol": "WBTC", "token_sold_symbol": "USDC", "chain": "ethereum",
             "trade_value_usd": 312_000, "trader_address_label": "Wintermute Trading",
             "trader_address": "0xf584f8728b874a6a5c7a8d4d387c9aae9172d621",
             "block_timestamp": "2026-03-23T21:00:00", "transaction_hash": "0xabc123"},
            {"token_bought_symbol": "PEPE", "token_sold_symbol": "ETH", "chain": "ethereum",
             "trade_value_usd": 48_000,  "trader_address_label": "",
             "trader_address": "0xdeadbeef",
             "block_timestamp": "2026-03-23T20:58:00", "transaction_hash": "0xdef456"},
        ]}
    },
    "screener_eth": {
        "success": True,
        "data": {"data": [
            {"token_symbol": "WBTC", "chain": "ethereum", "volume": 85_000_000, "market_cap_usd": 14_000_000_000, "price_change": 0.021},
            {"token_symbol": "LINK", "chain": "ethereum", "volume": 22_000_000, "market_cap_usd":  8_200_000_000, "price_change": 0.014},
            {"token_symbol": "PEPE", "chain": "ethereum", "volume": 18_000_000, "market_cap_usd":  3_100_000_000, "price_change": -0.053},
        ]}
    },
}
