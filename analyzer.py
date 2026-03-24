"""analyzer.py — Signal detection engine.

Rules:
  STRONG BUY   net_flow_usd  >  +500 000  AND smart_money_count >= 3
  STRONG SELL  net_flow_usd  <  -500 000  AND smart_money_count >= 3
  WHALE MOVE   single DEX trade value_usd > 250 000 by a labeled wallet
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import config


@dataclass
class Alert:
    signal:      str           # "STRONG BUY" | "STRONG SELL" | "WHALE MOVE"
    token:       str
    chain:       str
    flow_usd:    float         # net flow (netflow) or trade value (whale)
    sm_wallets:  int           # smart_money_count (0 for whale alerts)
    timestamp:   str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    label:       str = ""      # wallet label for whale moves
    extra:       str = ""      # free-form detail


def analyze_netflows(rows: list, chain: str) -> list[Alert]:
    """Detect STRONG BUY / STRONG SELL from netflow data."""
    alerts: list[Alert] = []

    for row in rows:
        symbol = row.get("token_symbol", "UNKNOWN")
        flow   = float(row.get("net_flow_usd", 0))
        count  = int(row.get("smart_money_count", 0))
        price  = row.get("price_usd", 0)
        pct    = row.get("price_change_pct", 0)

        if flow >= config.STRONG_FLOW_USD and count >= config.MIN_SM_WALLETS:
            alerts.append(Alert(
                signal     = "STRONG BUY",
                token      = symbol,
                chain      = chain,
                flow_usd   = flow,
                sm_wallets = count,
                extra      = f"Price: ${price:,.4f} ({pct:+.1f}% 1h)",
            ))

        elif flow <= -config.STRONG_FLOW_USD and count >= config.MIN_SM_WALLETS:
            alerts.append(Alert(
                signal     = "STRONG SELL",
                token      = symbol,
                chain      = chain,
                flow_usd   = flow,
                sm_wallets = count,
                extra      = f"Price: ${price:,.4f} ({pct:+.1f}% 1h)",
            ))

    return alerts


def analyze_dex_trades(rows: list, chain: str) -> list[Alert]:
    """Detect WHALE MOVE from DEX trade data."""
    alerts: list[Alert] = []
    STABLES = {"USDC", "USDT", "DAI", "BUSD", "USDH", "USDS"}

    for trade in rows:
        value  = float(trade.get("trade_value_usd", 0))
        label  = trade.get("trader_address_label", "")
        bought = trade.get("token_bought_symbol", "")
        sold   = trade.get("token_sold_symbol", "")
        ts     = trade.get("block_timestamp", "")
        tx     = trade.get("transaction_hash", "")[:12] + "..."

        if value < config.WHALE_TRADE_USD or not label:
            continue  # must be labeled wallet AND above threshold

        token = sold if bought.upper() in STABLES else bought

        alerts.append(Alert(
            signal     = "WHALE MOVE",
            token      = token,
            chain      = chain,
            flow_usd   = value,
            sm_wallets = 0,
            label      = label,
            extra      = f"Bought {bought} / Sold {sold} | tx {tx}",
        ))

    return alerts


def run_all(netflow_eth, netflow_sol, dex_eth) -> list[Alert]:
    """Aggregate all detectors and return unique alerts."""
    return (
        analyze_netflows(netflow_eth, "ethereum")
        + analyze_netflows(netflow_sol, "solana")
        + analyze_dex_trades(dex_eth, "ethereum")
    )
