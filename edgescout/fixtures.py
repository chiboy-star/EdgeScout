"""
Fixtures & Market View Engine for EdgeScout.
Integrates with football-data.org feed, manages upcoming fixtures,
manual SportyBet odds entry, Shin margin removal, and cost calculation.

Core Principle: Never claim an edge. Quantify bookmaker margin and expected loss.
Strict Labeling: Any fixture from sample/historical data carries is_demo = True and a visible DEMO badge.
"""
import requests
import json
import os
import sqlite3
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from pathlib import Path

from edgescout.config import DEFAULT_DB_PATH, CACHE_DIR
from edgescout.models.margin import remove_margin_shin, calculate_overround
from edgescout.data.football_data_org import FootballDataOrgClient


def get_risk_badge(overround_pct: Optional[float], min_odds: Optional[float], max_odds: Optional[float]) -> Dict[str, str]:
    """
    Computes an observable risk badge based strictly on factual properties:
    - High margin / vig
    - Longshot skew
    - Odds volatility
    """
    if overround_pct is None:
        return {
            'level': 'No Odds Loaded',
            'badge_class': 'muted',
            'reasons': ['Awaiting SportyBet odds entry']
        }

    reasons = []
    if overround_pct > 6.0:
        level = "High Vig ▲"
        reasons.append(f"Excessive bookmaker margin ({overround_pct:.1f}%)")
    elif overround_pct > 4.5:
        level = "Standard Vig ■"
        reasons.append(f"Typical soft-book margin ({overround_pct:.1f}%)")
    else:
        level = "Competitive Vig ●"
        reasons.append(f"Competitive sharp margin ({overround_pct:.1f}%)")

    if max_odds and max_odds >= 6.0:
        reasons.append("High outcome variance (heavy underdog)")
    elif min_odds and min_odds >= 2.2:
        reasons.append("Tightly contested coin-flip market")

    return {
        'level': level,
        'badge_class': 'alert' if 'High' in level else ('lavender' if 'Standard' in level else 'muted'),
        'reasons': reasons
    }


def analyze_fixture_market(
    match_id: str,
    home_team: str,
    away_team: str,
    league_name: str,
    kickoff_time: str,
    odds_1x2: Optional[List[float]] = None,
    bookmaker: str = "SportyBet (User Entry)",
    is_demo: bool = False,
    feed_source: str = "football-data.org"
) -> Dict[str, Any]:
    """
    Computes true margin-removed probabilities, margin %, and cost per 1,000 staked.
    If odds_1x2 is None, outputs clean 'no odds loaded' state ready for user entry.
    """
    has_odds = odds_1x2 is not None and len(odds_1x2) == 3 and all(o > 1.0 for o in odds_1x2)

    if not has_odds:
        return {
            'match_id': match_id,
            'home_team': home_team,
            'away_team': away_team,
            'league': league_name,
            'kickoff_time': kickoff_time,
            'bookmaker': bookmaker,
            'has_odds': False,
            'is_demo': is_demo,
            'feed_source': feed_source,
            'overround_pct': None,
            'dominant_category': "No Odds Loaded",
            'dominant_disclaimer': "Awaiting user SportyBet odds entry.",
            'risk_badge': get_risk_badge(None, None, None),
            'outcomes': [],
            'raw_odds': None,
            'updated_at': "Just now"
        }

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
        'has_odds': True,
        'is_demo': is_demo,
        'feed_source': feed_source,
        'overround_pct': overround_pct,
        'dominant_category': dominant_cat,
        'dominant_disclaimer': "Market view from bookmaker price, NOT an edge.",
        'risk_badge': risk,
        'outcomes': outcomes,
        'raw_odds': odds_1x2,
        'updated_at': "Just now"
    }


def get_market_fixtures(api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns upcoming fixtures fetched from football-data.org (or cached real slate).
    Properly labels is_demo=True with visible DEMO badge if demo/sample data is used.
    """
    client = FootballDataOrgClient(api_key=api_key)
    raw_fixtures, is_demo = client.fetch_upcoming_fixtures()
    results = []

    for f in raw_fixtures:
        analyzed = analyze_fixture_market(
            match_id=f['match_id'],
            home_team=f['home_team'],
            away_team=f['away_team'],
            league_name=f['league'],
            kickoff_time=f['kickoff_time'],
            odds_1x2=f.get('odds'),
            bookmaker="SportyBet" if f.get('odds') else "No Odds Loaded",
            is_demo=is_demo or f.get('is_demo', False),
            feed_source=f.get('feed_source', 'football-data.org')
        )
        results.append(analyzed)

    return results
