"""notifier.py — Telegram alert sender via python-telegram-bot."""

import asyncio
from typing import TYPE_CHECKING
import requests

import config
import insight_generator

if TYPE_CHECKING:
    from analyzer import Alert

_SIGNAL_EMOJI = {
    "STRONG BUY":  "🟢",
    "STRONG SELL": "🔴",
    "WHALE MOVE":  "🐋",
}

_CHAIN_EMOJI = {
    "ethereum": "⟠",
    "solana":   "◎",
}


def format_message(alert: "Alert") -> str:
    """Build the Telegram message string."""
    sig_emoji   = _SIGNAL_EMOJI.get(alert.signal, "⚡")
    chain_emoji = _CHAIN_EMOJI.get(alert.chain.lower(), "🔗")
    flow_str    = f"${abs(alert.flow_usd):,.0f}"
    direction   = "+" if alert.flow_usd >= 0 else "-"

    lines = [
        "🚨 *SMART MONEY ALERT*",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📌 Token:      *{alert.token}*",
        f"{chain_emoji}  Chain:      {alert.chain.capitalize()}",
        f"{sig_emoji} Signal:     *{alert.signal}*",
        f"💰 Flow:       {direction}{flow_str}",
    ]

    if alert.signal != "WHALE MOVE":
        lines.append(f"👛 SM Wallets: {alert.sm_wallets}")
    else:
        lines.append(f"🏷️  Wallet:     {alert.label}")

    lines.append(f"⭐ Score:       *{alert.score:.1f}/10*")

    insight = insight_generator.generate_insight(alert)
    lines.append("")
    lines.append(f"🧠 *Insight:* {insight}")

    lines += [
        f"⏰ Time:       {alert.timestamp}",
        "━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if alert.extra:
        lines.append(f"ℹ️  {alert.extra}")

    lines += [
        "",
        "_Powered by @nansen\\_ai #NansenCLI_",
    ]

    return "\n".join(lines)


def format_console(alert: "Alert") -> str:
    """Plain-text version for terminal display."""
    return format_message(alert).replace("*", "").replace("_", "")


async def _send_async(alert: "Alert", message: str):
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    
    chain_slug = "ethereum" if "eth" in alert.chain.lower() else "solana" if "sol" in alert.chain.lower() else alert.chain.lower()
    url = f"https://dexscreener.com/{chain_slug}/{alert.token.lower()}"
    
    keyboard = [[InlineKeyboardButton("📊 DexScreener Chart", url=url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await bot.send_message(
        chat_id      = config.TELEGRAM_CHAT_ID,
        text         = message,
        parse_mode   = "Markdown",
        reply_markup = reply_markup,
    )


def send(alert: "Alert", dry_run: bool = False) -> bool:
    """
    Send alert to Telegram. Returns True on success.
    dry_run=True skips Telegram and prints only to console.
    """
    msg     = format_message(alert)
    console = format_console(alert)

    # Always print to terminal
    print("\n" + "!" * 52)
    print(console)
    print("!" * 52 + "\n")

    if dry_run or not config.TELEGRAM_BOT_TOKEN:
        print("  [DRY RUN — Telegram not sent]\n")
        return True

    # Discord sending
    if config.DISCORD_WEBHOOK_URL and not dry_run:
        try:
            requests.post(config.DISCORD_WEBHOOK_URL, json={"content": msg})
            print("  ✅  Discord alert sent!")
        except Exception as e:
            print(f"  ⚠️  Discord error: {e}")

    try:
        asyncio.run(_send_async(alert, msg))
        print("  ✅  Telegram alert sent!\n")
        return True
    except Exception as e:
        print(f"  ⚠️  Telegram error: {e}\n")
        return False
