"""logger.py — Dedup alert log.

Stores fired alerts in alerts_log.json.
Suppresses the same (token, signal) pair within ALERT_COOLDOWN_HOURS.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import config

if TYPE_CHECKING:
    from analyzer import Alert


def _load() -> list[dict]:
    if not os.path.exists(config.ALERTS_LOG_FILE):
        return []
    try:
        with open(config.ALERTS_LOG_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save(records: list[dict]):
    with open(config.ALERTS_LOG_FILE, "w") as f:
        json.dump(records, f, indent=2)


def is_duplicate(alert: "Alert") -> bool:
    """Return True if an identical (token+chain+signal) alert was sent within cooldown."""
    records  = _load()
    cutoff   = datetime.now(timezone.utc) - timedelta(hours=config.ALERT_COOLDOWN_HOURS)
    key      = f"{alert.token}:{alert.chain}:{alert.signal}"

    for r in records:
        if r.get("key") != key:
            continue
        try:
            fired_at = datetime.fromisoformat(r["fired_at"])
            if fired_at.tzinfo is None:
                fired_at = fired_at.replace(tzinfo=timezone.utc)
            if fired_at >= cutoff:
                return True          # duplicate within window
        except (KeyError, ValueError):
            continue

    return False


import insight_generator

def record(alert: "Alert"):
    """Append a fired alert to the log and generate output signal."""
    records = _load()
    records.append({
        "key":      f"{alert.token}:{alert.chain}:{alert.signal}",
        "token":    alert.token,
        "chain":    alert.chain,
        "signal":   alert.signal,
        "flow_usd": alert.flow_usd,
        "fired_at": datetime.now(timezone.utc).isoformat(),
    })
    _save(records)
    
    # ── Save production-grade signals ────────────────────
    out_file = "outputs/signals.json"
    signals = []
    if os.path.exists(out_file):
        try:
            with open(out_file, "r") as f:
                signals = json.load(f)
        except Exception:
            pass
            
    signals = signals[-49:]  # keep last 50
    signals.append({
        "token": alert.token,
        "signal_type": alert.signal,
        "confidence_score": round(alert.score * 10, 1), # 0-100 scale 
        "explanation": insight_generator.generate_insight(alert),
        "chain": alert.chain,
        "flow_usd": alert.flow_usd,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    with open(out_file, "w") as f:
        json.dump(signals, f, indent=2)


def recent_alerts(hours: int = 24) -> list[dict]:
    """Return all alerts from the last N hours (for summary display)."""
    records = _load()
    cutoff  = datetime.now(timezone.utc) - timedelta(hours=hours)
    out     = []
    for r in records:
        try:
            fired_at = datetime.fromisoformat(r["fired_at"])
            if fired_at.tzinfo is None:
                fired_at = fired_at.replace(tzinfo=timezone.utc)
            if fired_at >= cutoff:
                out.append(r)
        except (KeyError, ValueError):
            continue
    return out
