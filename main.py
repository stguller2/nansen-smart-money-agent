#!/usr/bin/env python3
"""main.py — Entry point & scheduler.

Usage:
    # Normal mode (runs every 30 min, requires all env vars):
    python main.py

    # Demo mode (uses built-in sample data, no Nansen/Telegram needed):
    python main.py --demo

    # Single poll and exit:
    python main.py --once
"""

import argparse
import sys
import time
from datetime import datetime, timezone

import schedule

import analyzer
import config
import fetcher
import logger
import notifier


# ─────────────────────────────────────────────────────────
# Core poll function
# ─────────────────────────────────────────────────────────

def poll(demo: bool = False):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    print(f"\n{'─'*52}")
    print(f"  🔍  Polling Nansen  [{ts}]")
    print(f"{'─'*52}")

    # Fetch all data sources dynamically
    data_by_chain = {}
    
    for chain in config.CHAINS:
        print(f"  📡  Fetching Smart Money netflows ({chain.capitalize()})...")
        netflows = fetcher.fetch_netflow(chain, demo=demo)
        print(f"       {len(netflows)} token(s) returned")

        print(f"  📡  Fetching DEX trades ({chain.capitalize()})...")
        dexes = fetcher.fetch_dex_trades(chain, demo=demo)
        print(f"       {len(dexes)} trade(s) returned")

        data_by_chain[chain] = (netflows, dexes)

    # Optional: fetch screener for extra data if needed elsewhere
    print(f"  📡  Fetching token screener (Ethereum)...")
    screener_eth = fetcher.fetch_token_screener("ethereum", demo=demo)
    print(f"       {len(screener_eth)} token(s) returned")

    print(f"\n  📊  Total API calls so far: {fetcher.total_calls}")

    # Run analyzers
    alerts = analyzer.run_all(data_by_chain)

    if not alerts:
        print("\n  ✅  No signals triggered this cycle.")
        return

    print(f"\n  🔔  {len(alerts)} signal(s) detected!")

    fired = 0
    for alert in alerts:
        if logger.is_duplicate(alert):
            print(f"  ⏭️   Skipping duplicate: {alert.token} / {alert.signal}")
            continue

        dry = demo or not config.TELEGRAM_BOT_TOKEN
        if notifier.send(alert, dry_run=dry):
            logger.record(alert)
            fired += 1

    print(f"  ✅  {fired} new alert(s) sent.")


# ─────────────────────────────────────────────────────────
# Startup banner
# ─────────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════╗
║    🤖  Nansen Smart Money Alert Agent                ║
║    Monitoring ETH + SOL for whale movements          ║
╠══════════════════════════════════════════════════════╣
║  Signals:   STRONG BUY | STRONG SELL | WHALE MOVE   ║
║  Thresholds: Flow $500k | Whale $250k | SM >= 3      ║
║  Dedup:      2-hour cooldown per (token, signal)     ║
╚══════════════════════════════════════════════════════╝"""


# ─────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Nansen Smart Money Alert Agent")
    parser.add_argument("--demo", action="store_true", help="Run with sample data (no API keys needed)")
    parser.add_argument("--once", action="store_true", help="Run a single poll and exit")
    args = parser.parse_args()

    print(BANNER)

    if args.demo:
        print("\n  ⚡  DEMO MODE — using built-in sample data\n")
    else:
        config.validate()   # exits with error if keys missing
        print(f"\n  ✅  All env vars loaded")
        print(f"  ⏱️   Polling every {config.POLL_INTERVAL_MIN} minutes")
        if config.TELEGRAM_BOT_TOKEN:
            print(f"  📲  Telegram: configured")
        else:
            print(f"  📲  Telegram: not set (console output only)")

    # First poll immediately
    poll(demo=args.demo)

    if args.once or args.demo:
        # Show API call summary and exit
        print(f"\n{'═'*52}")
        print(f"  📊  SESSION SUMMARY")
        print(f"{'─'*52}")
        print(f"  Total Nansen API calls : {fetcher.total_calls}")
        print(f"  Eligibility (>= 10)    : {'✅ ELIGIBLE' if fetcher.total_calls >= 10 else '❌ Need more calls'}")
        recent = logger.recent_alerts(24)
        if recent:
            print(f"\n  📋  Alerts fired (last 24h):")
            for r in recent:
                print(f"       [{r['fired_at'][:16]}] {r['signal']} {r['token']} ({r['chain']})")
        print(f"{'═'*52}\n")
        return

    # Schedule recurring polls
    schedule.every(config.POLL_INTERVAL_MIN).minutes.do(poll, demo=args.demo)
    print(f"\n  ⏳  Next poll in {config.POLL_INTERVAL_MIN} min. Press Ctrl+C to stop.\n")

    try:
        while True:
            schedule.run_pending()
            time.sleep(10)
    except KeyboardInterrupt:
        print(f"\n\n  👋  Stopped. Total API calls: {fetcher.total_calls}")
        sys.exit(0)


if __name__ == "__main__":
    main()
