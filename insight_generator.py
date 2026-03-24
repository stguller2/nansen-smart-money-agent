"""
insight_generator.py — Converts algorithmic signals into human-readable quantitative alpha.
Acts as a mock-LLM to output "Trading Desk" style insights.
"""

def generate_insight(alert) -> str:
    """Generate a human-readable, quantitative explanation for a signal."""
    
    if alert.signal == "STRONG BUY":
        return (f"{alert.sm_wallets} smart money wallets heavily accumulated {alert.token} "
                f"in the last 1 hour across {alert.chain.capitalize()}. "
                f"Total net inflow stands at +${alert.flow_usd:,.0f}. "
                f"This indicates a potential early accumulation or cluster buying phase.")
                
    elif alert.signal == "STRONG SELL":
        return (f"{alert.sm_wallets} smart money wallets have been offloading {alert.token} "
                f"on {alert.chain.capitalize()}. Net outflow reached -${abs(alert.flow_usd):,.0f} "
                f"in the last hour, signaling potential exhaustion or rotation out of this asset.")
                
    elif alert.signal == "WHALE MOVE":
        wallet = alert.label if alert.label else "A large tagged entity"
        return (f"A sudden position change detected! {wallet} executed a "
                f"massive DEX swap worth ${alert.flow_usd:,.0f} involving {alert.token} "
                f"on {alert.chain.capitalize()}. Watch out for immediate volatility.")
                
    return f"Smart money activity detected for {alert.token}. Flow: ${alert.flow_usd:,.0f}."
