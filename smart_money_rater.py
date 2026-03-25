"""
🚨 Smart Money Signal Rater
Powered by Nansen CLI — Pure algorithmic scoring, no external AI needed.

Usage:
    nansen login --api-key YOUR_KEY
    python smart_money_rater.py

Dependencies:
    pip install pandas matplotlib
"""

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


# ─────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────

CHAIN   = "solana"         # change to "ethereum" if needed
DELAY   = 1.2              # seconds between API calls (rate limiting)
API_CALL_COUNT = 0         # global counter


# ─────────────────────────────────────────────────────────
# NANSEN CLI WRAPPER
# ─────────────────────────────────────────────────────────

ALLOWED_SUBCOMMANDS = {
    "research smart-money dex-trades",
    "research smart-money netflow",
    "research smart-money holdings",
    "research token screener",
    "research token flows",
    "research token who-bought-sold",
}

def run_nansen(subcommand: str, extra_args: str = "", retries: int = 3) -> dict:
    """Run a Nansen CLI command and return parsed JSON. Counts API calls."""
    global API_CALL_COUNT

    base = " ".join(subcommand.strip().split()[:3])
    if base not in ALLOWED_SUBCOMMANDS:
        return {"error": f"Command not in allowlist: {base}"}

    cmd = f"nansen {subcommand} {extra_args} --output json".strip()

    for attempt in range(1, retries + 1):
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30
            )
            time.sleep(DELAY)
            data = json.loads(result.stdout)
            API_CALL_COUNT += 1
            return data
        except json.JSONDecodeError:
            stderr = result.stderr[:120] if result.stderr else ""
            print(f"  ⚠️  JSON parse error (attempt {attempt}). {stderr}")
            if attempt < retries:
                backoff = 2 ** attempt
                print(f"  🔄 Retrying in {backoff}s...")
                time.sleep(backoff)
            else:
                return {"raw": result.stdout, "error": result.stderr}
        except subprocess.TimeoutExpired:
            print(f"  ⏰ Timeout (attempt {attempt})")
            if attempt < retries:
                time.sleep(2 ** attempt)
            else:
                return {"error": "Timeout after all retries"}

    return {"error": "Unexpected exit"}


def safe_list(data: dict) -> list:
    """Safely extract a list from Nansen's nested response."""
    if not data or "error" in data:
        return []
    inner = data.get("data", data)
    if isinstance(inner, dict):
        inner = inner.get("data", [])
    return inner if isinstance(inner, list) else []


# ─────────────────────────────────────────────────────────
# SCORING ENGINE
# ─────────────────────────────────────────────────────────

def score_dex_trades(trades: list, token_symbol: str) -> tuple[float, list]:
    """
    Score based on Smart Money DEX trade direction for a specific token.
    Returns (score 0-4, findings list)
    """
    findings = []
    if not trades:
        return 0.0, ["No DEX trade data available"]

    token_sym = token_symbol.upper()
    buy_vol = sum(
        t.get("trade_value_usd", 0)
        for t in trades
        if t.get("token_bought_symbol", "").upper() == token_sym
    )
    sell_vol = sum(
        t.get("trade_value_usd", 0)
        for t in trades
        if t.get("token_sold_symbol", "").upper() == token_sym
    )
    buy_count = sum(1 for t in trades if t.get("token_bought_symbol", "").upper() == token_sym)
    sell_count = sum(1 for t in trades if t.get("token_sold_symbol", "").upper() == token_sym)
    total_vol = buy_vol + sell_vol

    if total_vol == 0:
        # Token not found in recent SM trades — use overall volume as context signal
        total_trades = len(trades)
        avg_val = sum(t.get("trade_value_usd", 0) for t in trades) / max(total_trades, 1)
        findings.append(f"Token not in recent SM DEX trades (market active: {total_trades} trades, avg ${avg_val:,.0f})")
        return 1.0, findings

    ratio = buy_vol / total_vol  # >0.5 = more buying
    net_usd = buy_vol - sell_vol

    findings.append(f"SM DEX buy vol: ${buy_vol:,.0f} ({buy_count} trades) | sell vol: ${sell_vol:,.0f} ({sell_count} trades)")
    findings.append(f"Net SM flow: {'+'if net_usd>=0 else ''}{net_usd:,.0f} USD ({ratio*100:.1f}% buying pressure)")

    if ratio >= 0.75:
        score = 4.0
    elif ratio >= 0.6:
        score = 3.0
    elif ratio >= 0.4:
        score = 2.0
    else:
        score = 1.0

    return score, findings


def score_netflow(netflows: list, token_symbol: str) -> tuple[float, list]:
    """
    Score based on net capital flows. Returns (score 0-3, findings)
    """
    findings = []
    if not netflows:
        return 0.0, ["No netflow data available"]

    token_sym = token_symbol.upper()
    matches = [
        n for n in netflows
        if n.get("token_symbol", "").upper() == token_sym
    ]

    if not matches:
        # Use overall market netflow as context
        total_inflow  = sum(n.get("inflow_usd", 0) for n in netflows)
        total_outflow = sum(n.get("outflow_usd", 0) for n in netflows)
        net = total_inflow - total_outflow
        findings.append(f"Token not in SM netflows. Market net: {'+'if net>=0 else ''}{net:,.0f} USD")
        return 1.0, findings

    inflow  = sum(m.get("inflow_usd", 0) for m in matches)
    outflow = sum(m.get("outflow_usd", 0) for m in matches)
    net     = inflow - outflow

    findings.append(f"SM netflow — inflow: ${inflow:,.0f} | outflow: ${outflow:,.0f} | net: {'+'if net>=0 else ''}{net:,.0f}")

    if net > 500_000:
        score = 3.0
    elif net > 0:
        score = 2.0
    elif net > -500_000:
        score = 1.0
    else:
        score = 0.0

    return score, findings


def score_screener(screener_rows: list, token_symbol: str) -> tuple[float, list]:
    """
    Score based on token screener metrics. Returns (score 0-3, findings)
    """
    findings = []
    if not screener_rows:
        return 0.0, ["No screener data available"]

    token_sym = token_symbol.upper()
    match = next(
        (r for r in screener_rows if r.get("token_symbol", "").upper() == token_sym),
        None
    )

    if not match:
        findings.append(f"Token {token_sym} not found in top screener results")
        return 0.5, findings

    price_change = match.get("price_change", 0) * 100
    inflow_ratio = match.get("inflow_fdv_ratio", 0)
    outflow_ratio = match.get("outflow_fdv_ratio", 0)
    net_ratio = inflow_ratio - outflow_ratio
    vol = match.get("volume", 0)
    mc = match.get("market_cap_usd", 0)

    findings.append(f"Price change 24h: {price_change:+.2f}% | Vol: ${vol:,.0f} | MCap: ${mc:,.0f}")
    findings.append(f"Inflow/FDV: {inflow_ratio:.4f} | Outflow/FDV: {outflow_ratio:.4f} | Net: {net_ratio:+.4f}")

    score = 0.0
    if price_change > 5:
        score += 1.0
    elif price_change > 0:
        score += 0.5

    if net_ratio > 0.002:
        score += 1.0
    elif net_ratio > 0:
        score += 0.5

    if vol > 10_000_000:
        score += 1.0
    elif vol > 1_000_000:
        score += 0.5

    return min(score, 3.0), findings


def compute_signal(token: str, dex_data: list, flow_data: list, screen_data: list) -> dict:
    """Combine all scores into a final 1-10 signal."""

    dex_score,   dex_findings   = score_dex_trades(dex_data, token)
    flow_score,  flow_findings  = score_netflow(flow_data, token)
    screen_score, screen_findings = score_screener(screen_data, token)

    # Weighted total out of 10
    raw = dex_score * (4/4) + flow_score * (3/3) + screen_score * (3/3)
    # Scale: max possible = 4+3+3 = 10
    final_score = round(min(dex_score + flow_score + screen_score, 10.0), 1)

    if final_score >= 7:
        direction  = "ACCUMULATING 📈"
        risk_level = "LOW"
    elif final_score >= 4:
        direction  = "NEUTRAL ↔️"
        risk_level = "MEDIUM"
    else:
        direction  = "EXITING 📉"
        risk_level = "HIGH"

    all_findings = dex_findings + flow_findings + screen_findings

    return {
        "token":      token,
        "score":      final_score,
        "direction":  direction,
        "risk":       risk_level,
        "findings":   all_findings,
    }


def print_report(r: dict):
    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 SMART MONEY SIGNAL REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 Token:         {r['token']}
📊 Signal Score:  {r['score']}/10
📈 Direction:     {r['direction']}

🔍 Key Findings:""")
    for f in r["findings"]:
        print(f"  - {f}")
    print(f"""
⚠️  Risk Level:   {r['risk']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")


# ─────────────────────────────────────────────────────────
# STEP 1 — SHARED DATA (broad market, 2 API calls)
# ─────────────────────────────────────────────────────────

print(f"\n🔗 Chain: {CHAIN.upper()}")
print("=" * 50)

print("\n⏳ Fetching Smart Money DEX trades...")
raw_dex = run_nansen("research smart-money dex-trades", f"--chain {CHAIN}")
dex_trades = safe_list(raw_dex)
print(f"  ✅ {len(dex_trades)} SM DEX trades loaded")

print("⏳ Fetching Smart Money netflows...")
raw_flow = run_nansen("research smart-money netflow", f"--chain {CHAIN}")
net_flows = safe_list(raw_flow)
print(f"  ✅ {len(net_flows)} netflow entries loaded")

print("⏳ Fetching token screener...")
raw_screen = run_nansen("research token screener", f"--chain {CHAIN}")
screener = safe_list(raw_screen)
print(f"  ✅ {len(screener)} tokens in screener")

print("⏳ Fetching Smart Money holdings...")
raw_holdings = run_nansen("research smart-money holdings", f"--chain {CHAIN}")
holdings = safe_list(raw_holdings)
print(f"  ✅ {len(holdings)} holding entries loaded")


# ─────────────────────────────────────────────────────────
# STEP 2 — TOP TOKENS FROM SCREENER
# ─────────────────────────────────────────────────────────

# Pick top 5 tokens from screener by 24h volume, skip stablecoins
STABLECOINS = {"USDC", "USDT", "BUSD", "DAI", "TUSD", "USDH", "USDS"}

top_tokens = [
    r["token_symbol"]
    for r in sorted(screener, key=lambda x: x.get("volume", 0), reverse=True)
    if r.get("token_symbol", "").upper() not in STABLECOINS
][:5]

print(f"\n🏆 Top tokens by SM volume: {', '.join(top_tokens)}")
print("=" * 50)


# ─────────────────────────────────────────────────────────
# STEP 3 — PER-TOKEN DEEP DIVE (2 API calls each)
# ─────────────────────────────────────────────────────────

all_reports = []

for token in top_tokens:
    # Find token address from screener
    token_row = next(
        (r for r in screener if r.get("token_symbol", "").upper() == token.upper()),
        None
    )
    token_addr = token_row.get("token_address", "") if token_row else ""

    print(f"\n⏳ Deep scan: {token} ({token_addr[:8]}...{token_addr[-6:] if len(token_addr)>14 else token_addr})")

    if token_addr:
        raw_flows = run_nansen("research token flows", f"--token {token_addr} --chain {CHAIN} --days 7")
        token_flows = safe_list(raw_flows)
        print(f"  ✅ Token flows: {len(token_flows)} entries")

        raw_wbs = run_nansen("research token who-bought-sold", f"--token {token_addr} --chain {CHAIN} --days 7")
        who_bs = safe_list(raw_wbs)
        print(f"  ✅ Who bought/sold: {len(who_bs)} entries")
    else:
        token_flows = []
        who_bs = []
        print("  ⚠️ No token address — skipping deep calls")

    # Compute signal from shared data
    signal = compute_signal(token, dex_trades, net_flows, screener)
    signal["token_address"] = token_addr
    signal["who_bought_sold_count"] = len(who_bs)
    signal["flow_entries"] = len(token_flows)

    # Enrich findings with per-token data
    if who_bs:
        smart_buyers  = sum(1 for w in who_bs if w.get("action", "").lower() == "buy")
        smart_sellers = sum(1 for w in who_bs if w.get("action", "").lower() == "sell")
        signal["findings"].append(
            f"SM wallets (7d): {smart_buyers} buyers | {smart_sellers} sellers"
        )

    all_reports.append(signal)
    print_report(signal)


# ─────────────────────────────────────────────────────────
# STEP 4 — BEST SIGNAL PICK
# ─────────────────────────────────────────────────────────

best = max(all_reports, key=lambda r: r["score"])
print(f"\n🏆 TODAY'S STRONGEST SIGNAL: {best['token']} ({best['score']}/10 — {best['direction']})")


# ─────────────────────────────────────────────────────────
# STEP 5 — VISUALIZATION
# ─────────────────────────────────────────────────────────

tokens = [r["token"] for r in all_reports]
scores = [r["score"] for r in all_reports]
colors = ["#e74c3c" if s < 4 else "#f39c12" if s < 7 else "#2ecc71" for s in scores]

fig, ax = plt.subplots(figsize=(10, 5))
bars = ax.bar(tokens, scores, color=colors, edgecolor="white", linewidth=1.5, width=0.55)

for bar, score, r in zip(bars, scores, all_reports):
    ax.text(
        bar.get_x() + bar.get_width() / 2,
        bar.get_height() + 0.18,
        f"{score}/10\n{r['direction'].split()[0]}",
        ha="center", va="bottom", fontsize=10, fontweight="bold", color="white",
    )

ax.set_ylim(0, 12)
ax.set_ylabel("Signal Score", fontsize=12, color="white")
ax.set_title(
    f"🚨 Smart Money Signal Rater — {CHAIN.capitalize()} | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
    fontsize=13, fontweight="bold", color="white", pad=14
)
ax.set_facecolor("#1a1a2e")
fig.patch.set_facecolor("#0f0f1a")
ax.tick_params(colors="white", labelsize=11)
ax.spines[:].set_color("#333")

legend = [
    mpatches.Patch(color="#2ecc71", label="Strong Signal (7-10)"),
    mpatches.Patch(color="#f39c12", label="Moderate (4-6)"),
    mpatches.Patch(color="#e74c3c", label="Weak (0-3)"),
]
ax.legend(handles=legend, loc="upper right", facecolor="#1a1a2e", labelcolor="white", fontsize=10)
plt.tight_layout()

chart_file = "smart_money_scores.png"
plt.savefig(chart_file, dpi=150, bbox_inches="tight")
plt.close()
print(f"\n💾 Chart saved → {chart_file}")


# ─────────────────────────────────────────────────────────
# STEP 6 — SAVE TO CSV
# ─────────────────────────────────────────────────────────

df = pd.DataFrame([
    {
        "token":       r["token"],
        "score":       r["score"],
        "direction":   r["direction"],
        "risk":        r["risk"],
        "findings":    " | ".join(r["findings"]),
        "analyzed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    for r in all_reports
]).sort_values("score", ascending=False).reset_index(drop=True)

csv_file = f"smart_money_{CHAIN}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.csv"
df.to_csv(csv_file, index=False)

print("\n📊 FINAL RANKINGS")
print("━" * 50)
print(df[["token", "score", "direction", "risk"]].to_string(index=False))
print("━" * 50)
print(f"💾 Report saved → {csv_file}")


# ─────────────────────────────────────────────────────────
# STEP 7 — API CALL SUMMARY
# ─────────────────────────────────────────────────────────

print(f"\n📊 NANSEN API CALL SUMMARY")
print("━" * 35)
print(f"Shared calls (DEX+Flow+Screen+Holdings) : 4")
print(f"Per-token deep calls ({len(top_tokens)} tokens × 2)   : {len(top_tokens) * 2}")
print("━" * 35)
print(f"TOTAL API CALLS  : {API_CALL_COUNT}")
print(f"Minimum required : 10")
status = "✅ ELIGIBLE" if API_CALL_COUNT >= 10 else "❌ Need more calls"
print(f"Status           : {status}")
