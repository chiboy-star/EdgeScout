"""
Fixtures & Market View Engine for EdgeScout.
Manages upcoming fixtures, manual SportyBet odds entry, margin calculation,
and market-implied categorization.
Core Principle: Never claim an edge. Quantify the bookmaker's profit margin and expected loss.
"""
import requests
import json
import os
import sqlite3
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from pathlib import Path

from edgescout.config import DEFAULT_DB_PATH, CACHE_DIR
from edgescout.models.margin import remove_margin_shin, calculate_overround


def get_risk_badge(overround_pct: float, min_odds: float, max_odds: float) -> Dict[str, str]:
    """
    Computes an observable risk badge based strictly on factual properties:
    - High margin / vig
    - Longshot skew
    - Odds volatility
    """
    reasons = []
    if overround_pct > 6.0:
        level = "High Risk ▲"
        reasons.append(f"Excessive bookmaker margin ({overround_pct:.1f}%)")
    elif overround_pct > 4.5:
        level = "Medium Risk ■"
        reasons.append(f"Standard soft-book margin ({overround_pct:.1f}%)")
    else:
        level = "Low Risk ●"
        reasons.append(f"Competitive sharp margin ({overround_pct:.1f}%)")

    if max_odds >= 6.0:
        reasons.append("High outcome variance (heavy underdog)")
    elif min_odds >= 2.2:
        reasons.append("Tightly contested coin-flip market")

    return {
        'level': level,
        'badge_class': 'alert' if 'High' in level else ('lavender' if 'Medium' in level else 'muted'),
        'reasons': reasons
    }


def analyze_fixture_market(
    match_id: str,
    home_team: str,
    away_team: str,
    league_name: str,
    kickoff_time: str,
    odds_1x2: List[float],
    bookmaker: str = "SportyBet (User Entry)"
) -> Dict[str, Any]:
    """
    Computes true margin-removed probabilities, margin %, and cost per 1,000 staked.
    Categorizes selections into: Market favourites (>=65%), Contested (35-65%), Longshots (<20%).
    """
    h_odd, d_odd, a_odd = odds_1x2
    overround = calculate_overround(odds_1x2)
    overround_pct = round(overround * 100.0, 2)
    fair_probs, z_param = remove_margin_shin(odds_1x2)

    selections = [
        ('Home', home_team, h_odd, float(fair_probs[0]), 'H'),
        ('Draw', 'Draw', d_odd, float(fair_probs[1]), 'D'),
        ('Away', away_team, a_odd, float(fair_probs[2]), 'A')
    ]

    outcomes = []
    max_prob = 0.0
    dominant_cat = "Contested (35-65%)"

    for label, name, odd, p_fair, sel_code in selections:
        implied_raw = (1.0 / odd) * 100.0
        fair_pct = p_fair * 100.0
        
        # Expected loss per 1,000 staked:
        # Loss = 1000 - 1000 * (p_fair * odd)
        expected_return_1000 = 1000.0 * (p_fair * odd)
        expected_loss_1000 = max(0.0, 1000.0 - expected_return_1000)

        # Market-implied category (NOT an edge)
        if fair_pct >= 65.0:
            category = "Market favourite (≥65%)"
        elif fair_pct >= 35.0:
            category = "Contested (35-65%)"
        elif fair_pct < 20.0:
            category = "Longshot (<20%)"
        else:
            category = "Moderate Underdog (20-35%)"

        if p_fair > max_prob:
            max_prob = p_fair
            dominant_cat = category

        outcomes.append({
            'selection': sel_code,
            'label': label,
            'name': name,
            'odds': odd,
            'raw_implied_prob_pct': round(implied_raw, 1),
            'fair_probability_pct': round(fair_pct, 1),
            'fair_odds': round(1.0 / p_fair, 2) if p_fair > 0 else 999.0,
            'expected_loss_per_1000': round(expected_loss_1000, 1),
            'category': category
        })

    risk = get_risk_badge(overround_pct, min(odds_1x2), max(odds_1x2))

    return {
        'match_id': match_id,
        'home_team': home_team,
        'away_team': away_team,
        'league': league_name,
        'kickoff_time': kickoff_time,
        'bookmaker': bookmaker,
        'overround_pct': overround_pct,
        'dominant_category': dominant_cat,
        'dominant_disclaimer': "Market view from bookmaker price, NOT an edge.",
        'risk_badge': risk,
        'outcomes': outcomes,
        'raw_odds': odds_1x2,
        'updated_at': "Just now"
    }


def get_sample_upcoming_fixtures() -> List[Dict[str, Any]]:
    """
    Returns realistic upcoming top-flight fixtures with baseline SportyBet/market odds
    ready for inspection or manual adjustment.
    """
    fixtures_data = [
        ("E0_2026_001", "Arsenal", "Chelsea", "Premier League", "Saturday 16:00", [1.85, 3.75, 4.20]),
        ("E0_2026_002", "Manchester City", "Liverpool", "Premier League", "Sunday 17:30", [2.05, 3.60, 3.50]),
        ("SP1_2026_003", "Real Madrid", "Barcelona", "La Liga", "Sunday 20:00", [2.15, 3.70, 3.20]),
        ("D1_2026_004", "Bayern Munich", "Borussia Dortmund", "Bundesliga", "Saturday 17:30", [1.45, 5.00, 6.50]),
        ("I1_2026_005", "Inter Milan", "Juventus", "Serie A", "Sunday 19:45", [1.95, 3.40, 4.10]),
        ("F1_2026_006", "Paris SG", "Marseille", "Ligue 1", "Sunday 20:45", [1.40, 5.25, 7.50]),
        ("E0_2026_007", "Aston Villa", "Newcastle", "Premier League", "Saturday 13:30", [2.40, 3.50, 2.90]),
        ("SP1_2026_008", "Atletico Madrid", "Sevilla", "La Liga", "Saturday 21:00", [1.60, 4.00, 5.75])
    ]

    results = []
    for m_id, h, a, l, k, odds in fixtures_data:
        analyzed = analyze_fixture_market(m_id, h, a, l, k, odds, bookmaker="SportyBet")
        results.append(analyzed)

    return results

