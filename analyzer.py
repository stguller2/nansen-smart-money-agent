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
    score:       float = 0.0   # 0.0 to 10.0 confidence score
    timestamp:   str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    label:       str = ""      # wallet label for whale moves
    extra:       str = ""      # free-form detail


def calculate_score(flow_usd: float, sm_wallets: int, is_whale: bool = False) -> float:
    """Calculate a 0-10 confidence score for the signal."""
    # Absolute flow is what matters for magnitude
    abs_flow = abs(flow_usd)
    
    if is_whale:
        # Whale score based purely on size. Base $250k = 5.0, $1M+ = 10.0
        score = 5.0 + ((abs_flow - config.WHALE_TRADE_USD) / 150_000)
    else:
        # Netflow score based on money size and number of smart wallets confirming it
        # $500k flow = 2.0 pts
        flow_pts = (abs_flow / config.STRONG_FLOW_USD) * 2.5
        # 3 wallets = 3.0 pts, 10 wallets = 10.0 pts
        wallet_pts = sm_wallets * 1.0
        score = flow_pts + wallet_pts

    return min(10.0, max(0.0, score))


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
            score = calculate_score(flow, count)
            alerts.append(Alert(
                signal     = "STRONG BUY",
                token      = symbol,
                chain      = chain,
                flow_usd   = flow,
                sm_wallets = count,
                score      = score,
                extra      = f"Price: ${price:,.4f} ({pct:+.1f}% 1h)",
            ))

        elif flow <= -config.STRONG_FLOW_USD and count >= config.MIN_SM_WALLETS:
            score = calculate_score(flow, count)
            alerts.append(Alert(
                signal     = "STRONG SELL",
                token      = symbol,
                chain      = chain,
                flow_usd   = flow,
                sm_wallets = count,
                score      = score,
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
        score = calculate_score(value, 0, is_whale=True)

        alerts.append(Alert(
            signal     = "WHALE MOVE",
            token      = token,
            chain      = chain,
            flow_usd   = value,
            sm_wallets = 0,
            score      = score,
            label      = label,
            extra      = f"Bought {bought} / Sold {sold} | tx {tx}",
        ))

    return alerts


def analyze_vip_wallets(rows: list, wallet_name: str, address: str) -> list[Alert]:
    """Detect significant transactions from tracked VIP wallets."""
    alerts: list[Alert] = []

    for tx in rows:
        value = float(tx.get("value_usd", 0) or tx.get("amount_usd", 0) or 0)
        
        if value < config.VIP_TX_USD_MIN:
            continue

        token = tx.get("token_symbol", tx.get("asset", "UNKNOWN"))
        hash_ = tx.get("transaction_hash", tx.get("hash", "0x"))[:10] + "..."
        from_adr = tx.get("from_address", "").lower()
        
        direction = "sold/sent" if from_adr == address.lower() else "bought/received"
        sign = -1.0 if from_adr == address.lower() else 1.0
        
        alerts.append(Alert(
            signal = "VIP WALLET",
            token = token,
            chain = "multi-chain", # Nansen profiler searches cross-chain
            flow_usd = value * sign,
            sm_wallets = 1,
            score = 10.0, # Complete 100/100 conviction for VIPs
            label = wallet_name,
            extra = f"{wallet_name} {direction} {token} | tx {hash_}"
        ))

    return alerts


def analyze_screener(rows: list, chain: str) -> list[Alert]:
    """Detect new, trending tokens based on volume anomalies and price action."""
    alerts: list[Alert] = []
    
    for tk in rows:
        symbol = tk.get("token_symbol", "UNKNOWN")
        volume = float(tk.get("volume", 0) or 0)
        mcap = float(tk.get("market_cap_usd", 0) or 0)
        price_change = float(tk.get("price_change", 0) or 0)
        
        # Kural: Nansen'in "Emerging Opportunities" (Use Case 4) konsepti için
        # Eğer hacim 10 Milyon doların üzerindeyse ve fiyat %1'den fazla artıyorsa:
        if volume >= 10_000_000 and price_change >= 0.01:
            score = min(10.0, price_change * 300) # Yapay zeka skoru (ör: %3 artış -> ~9 skor)
            alerts.append(Alert(
                signal = "TRENDING TOKEN",
                token = symbol,
                chain = chain,
                flow_usd = volume, # Para akışı olarak Gecelik Hacim kullanılıyor
                sm_wallets = 0,
                score = score,
                label = "Token Screener",
                extra = f"🔥 Trend Detected! Vol: ${volume:,.0f} | MCAP: ${mcap:,.0f} | Price Change: +{price_change*100:.1f}%"
            ))
            
    return alerts


def run_all(data_by_chain: dict, vip_data: dict = None, screener_data: list = None) -> list[Alert]:
    """Aggregate all detectors and return unique alerts for all chains."""
    alerts = []
    
    for chain, (netflows, dexes) in data_by_chain.items():
        alerts.extend(analyze_netflows(netflows, chain))
        alerts.extend(analyze_dex_trades(dexes, chain))
        
    if vip_data:
        for name, data_bundle in vip_data.items():
            alerts.extend(analyze_vip_wallets(data_bundle["rows"], name, data_bundle["address"]))
            
    if screener_data:
        alerts.extend(analyze_screener(screener_data, "ethereum"))
            
    return alerts
