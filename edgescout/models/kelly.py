"""
Kelly Criterion Staking Engine for EdgeScout.
Implements quarter-Kelly sizing with conservative risk limits:
- Quarter-Kelly multiplier (f* / 4)
- 2% single-bet bankroll cap
- 6% total daily bankroll exposure cap
"""
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from pydantic import BaseModel, Field


class BetRecommendation(BaseModel):
    match_id: str
    selection: str  # 'H', 'D', or 'A'
    odds: float
    model_prob: float
    market_prob: float
    edge: float
    raw_kelly_fraction: float
    suggested_fraction: float
    suggested_stake: float
    tier: str = "Value"


def kelly_fraction(p: float, odds: float, multiplier: float = 0.25) -> float:
    """
    Calculate the fractional Kelly stake.
    Formula:
      b = odds - 1
      q = 1 - p
      f* = (b*p - q) / b = (p*odds - 1) / (odds - 1)
      suggested = multiplier * f*
    
    If edge <= 0 (EV <= 0), returns 0.0.
    """
    if odds <= 1.0 or p <= 0.0 or p >= 1.0:
        return 0.0
    
    edge = (p * odds) - 1.0
    if edge <= 0.0:
        return 0.0
    
    b = odds - 1.0
    f_star = edge / b
    return float(max(0.0, f_star * multiplier))


def calculate_stake(
    p: float,
    odds: float,
    bankroll: float,
    kelly_mult: float = 0.25,
    max_bet_fraction: float = 0.02
) -> Tuple[float, float, float]:
    """
    Calculate single bet sizing with quarter-Kelly and single-bet cap.
    
    Returns:
      (raw_fraction, capped_fraction, currency_stake)
    """
    raw_frac = kelly_fraction(p, odds, multiplier=kelly_mult)
    capped_frac = min(raw_frac, max_bet_fraction)
    stake = round(capped_frac * bankroll, 2)
    return raw_frac, capped_frac, stake


def allocate_daily_portfolio(
    bets: List[Dict[str, Any]],
    bankroll: float,
    kelly_mult: float = 0.25,
    max_bet_fraction: float = 0.02,
    max_daily_exposure: float = 0.06
) -> List[BetRecommendation]:
    """
    Allocates stakes across all qualifying bets for a single day.
    Enforces:
    1. Quarter-Kelly sizing
    2. Single-bet cap (max 2% bankroll)
    3. Daily portfolio cap (max 6% total exposure across all simultaneous bets).
       If sum(fractions) > max_daily_exposure, fractions are scaled down proportionally.
    """
    recommendations: List[BetRecommendation] = []
    
    # First pass: calculate individual capped stakes
    temp_bets = []
    total_requested_fraction = 0.0
    
    for bet in bets:
        p = float(bet["model_prob"])
        odds = float(bet["odds"])
        m_prob = float(bet.get("market_prob", 1.0 / odds))
        edge = (p * odds) - 1.0
        
        if edge <= 0.0:
            continue
            
        raw_f = kelly_fraction(p, odds, multiplier=kelly_mult)
        capped_f = min(raw_f, max_bet_fraction)
        
        if capped_f > 0.0:
            temp_bets.append({
                "bet": bet,
                "p": p,
                "odds": odds,
                "m_prob": m_prob,
                "edge": edge,
                "raw_f": raw_f,
                "capped_f": capped_f
            })
            total_requested_fraction += capped_f
            
    if not temp_bets:
        return []
        
    # Scale down if portfolio exposure exceeds daily cap
    scale_factor = 1.0
    if total_requested_fraction > max_daily_exposure:
        scale_factor = max_daily_exposure / total_requested_fraction
        
    for item in temp_bets:
        final_frac = item["capped_f"] * scale_factor
        stake = round(final_frac * bankroll, 2)
        
        # Determine default tier
        tier = "Value"
        if item["p"] >= 0.55 and item["edge"] >= 0.05:
            tier = "High Confidence"
        elif item["odds"] >= 5.0:
            tier = "Long Shot"
            
        rec = BetRecommendation(
            match_id=str(item["bet"].get("match_id", "")),
            selection=str(item["bet"].get("selection", "H")),
            odds=item["odds"],
            model_prob=round(item["p"], 4),
            market_prob=round(item["m_prob"], 4),
            edge=round(item["edge"], 4),
            raw_kelly_fraction=round(item["raw_f"], 4),
            suggested_fraction=round(final_frac, 4),
            suggested_stake=stake,
            tier=tier
        )
        recommendations.append(rec)
        
    return recommendations
