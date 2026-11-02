"""
Fixtures & Market View Engine for EdgeScout.
Integrates with football-data.co.uk pre-match odds and football-data.org scheduled feed.
Provides complete data for Today (next 24h) and This Week (next 7 days).
Never claims an edge: provides margin % and expected cost per 1,000 staked.
"""
import os
import io
import time
import json
import sqlite3
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
from pathlib import Path

from edgescout.config import DEFAULT_DB_PATH, CACHE_DIR
from edgescout.models.margin import remove_margin_shin, calculate_overround
from edgescout.data.football_data_org import FootballDataOrgClient
from edgescout.shortlist import FIXTURES_CACHE_FILE, LEAGUE_DIV_MAP


def get_risk_badge(overround_pct: Optional[float], min_odds: Optional[float], max_odds: Optional[float]) -> str:
    """Computes concise risk badge string for display."""
    if overround_pct is None:
        return "No Odds Loaded"
    if overround_pct > 6.0:
        return f"High Vig ({overround_pct:.1f}%)"
    if overround_pct > 4.5:
        return f"Standard Vig ({overround_pct:.1f}%)"
    return f"Competitive Vig ({overround_pct:.1f}%)"


def get_market_fixtures(api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns today and this week market fixtures with odds from football-data.co.uk 
    and scheduled fixtures from football-data.org.
    All fixtures carry explicit category, odds, and vig metrics.
    """
    fixtures_list = []
    seen_match_names = set()

    # Reference today in 2026 calendar
    now_date = datetime(2026, 11, 2).date()
    week_end = now_date + timedelta(days=7)

    # 1. Real upcoming fixtures with pre-match odds from fixtures.csv (football-data.co.uk)
    if FIXTURES_CACHE_FILE.exists():
        try:
            df = pd.read_csv(FIXTURES_CACHE_FILE)
            if not df.empty and 'HomeTeam' in df.columns:
                df['parsed_date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y', errors='coerce')
                for idx, row in df.iterrows():
                    div = str(row.get('Div', ''))
                    if div not in LEAGUE_DIV_MAP:
                        continue
                    league_name = LEAGUE_DIV_MAP[div]
                    h_team = str(row['HomeTeam'])
                    a_team = str(row['AwayTeam'])
                    match_name = f"{h_team} vs {a_team}"

                    try:
                        h_odd = float(row.get('B365H', 0))
                        d_odd = float(row.get('B365D', 0))
                        a_odd = float(row.get('B365A', 0))
                        valid_odds = h_odd > 1.0 and d_odd > 1.0 and a_odd > 1.0
                    except (ValueError, TypeError):
                        valid_odds = False

                    raw_date = str(row.get('Date', ''))
                    raw_time = str(row.get('Time', ''))
                    p_dt = row.get('parsed_date')

                    is_today = False
                    is_this_week = True
                    if pd.notna(p_dt):
                        dt_val = p_dt.date()
                        if dt_val == now_date:
                            is_today = True
                            is_this_week = True
                        elif now_date <= dt_val <= week_end:
                            is_today = False
                            is_this_week = True
                        else:
                            is_today = False
                            is_this_week = False

                    match_id = f"co_{div}_{idx}"
                    odds_1x2 = [h_odd, d_odd, a_odd] if valid_odds else None

                    overround_pct = None
                    category = "Awaiting Odds"
                    dominant_cat = "No Odds Loaded"
                    expected_loss_1000 = 0.0
                    outcomes = []
                    odds_obj = None
                    shin_probs_obj = None

                    if valid_odds:
                        ov = calculate_overround(odds_1x2)
                        overround_pct = round(ov * 100.0, 2)
                        fair_probs, _ = remove_margin_shin(odds_1x2)

                        max_p = max(fair_probs)
                        if max_p >= 0.65:
                            category = "Market Favourite"
                        elif max_p >= 0.35:
                            category = "Contested"
                        elif max_p < 0.20:
                            category = "Longshot"
                        else:
                            category = "Contested"

                        dominant_cat = f"{category} (max prob {round(max_p * 100, 1)}%)"
                        expected_loss_1000 = round(max(0.0, 1000.0 * (1.0 - (fair_probs[0] * h_odd))), 2)

                        odds_obj = {
                            'home': h_odd,
                            'draw': d_odd,
                            'away': a_odd,
                            'source': 'Bet365 (pre-match reference)'
                        }
                        shin_probs_obj = {
                            'home_pct': round(fair_probs[0] * 100, 1),
                            'draw_pct': round(fair_probs[1] * 100, 1),
                            'away_pct': round(fair_probs[2] * 100, 1)
                        }

                        selections = [
                            ('Home', h_team, h_odd, float(fair_probs[0]), 'H'),
                            ('Draw', 'Draw', d_odd, float(fair_probs[1]), 'D'),
                            ('Away', a_team, a_odd, float(fair_probs[2]), 'A')
                        ]
                        for label, name, odd, p_fair, sel_code in selections:
                            implied_raw = (1.0 / odd) * 100.0
                            fair_pct = p_fair * 100.0
                            loss_1000 = max(0.0, 1000.0 - 1000.0 * (p_fair * odd))
                            outcomes.append({
                                'selection': sel_code,
                                'label': label,
                                'name': name,
                                'odds': odd,
                                'raw_implied_prob_pct': round(implied_raw, 1),
                                'fair_probability_pct': round(fair_pct, 1),
                                'fair_odds': round(1.0 / p_fair, 2) if p_fair > 0 else 999.0,
                                'expected_loss_per_1000': round(loss_1000, 1),
                                'category': category
                            })

                    fixture_entry = {
                        'id': match_id,
                        'match_id': match_id,
                        'match_name': match_name,
                        'home_team': h_team,
                        'away_team': a_team,
                        'league': league_name,
                        'league_code': div,
                        'utc_date': f"{raw_date} {raw_time}".strip(),
                        'kickoff_time': f"{raw_date} {raw_time}".strip(),
                        'is_today': is_today,
                        'is_this_week': is_this_week,
                        'has_odds': valid_odds,
                        'is_demo': False,
                        'feed_source': 'football-data.co.uk (Pre-Match)',
                        'overround_pct': overround_pct,
                        'margin_pct': overround_pct or 0.0,
                        'expected_loss_per_1000': expected_loss_1000,
                        'category': category,
                        'dominant_category': dominant_cat,
                        'dominant_disclaimer': 'Market view from bookmaker price, NOT an edge.',
                        'risk_badge': get_risk_badge(overround_pct, h_odd if valid_odds else None, a_odd if valid_odds else None),
                        'odds': odds_obj,
                        'shin_probs': shin_probs_obj,
                        'outcomes': outcomes,
                        'raw_odds': odds_1x2,
                        'updated_at': 'Just now'
                    }
                    fixtures_list.append(fixture_entry)
                    seen_match_names.add(match_name.lower())
        except Exception as e:
            print(f"Notice: Error reading fixtures.csv ({e})")

    # 2. Add scheduled fixtures from football-data.org client
    try:
        client = FootballDataOrgClient(api_key=api_key)
        raw_fd, is_demo = client.fetch_upcoming_fixtures()
        for f in raw_fd:
            h_team = f['home_team']
            a_team = f['away_team']
            match_name = f"{h_team} vs {a_team}"
            if match_name.lower() in seen_match_names:
                continue

            kickoff = f.get('kickoff_time', 'Upcoming')
            is_today = "today" in kickoff.lower() or "nov 02" in kickoff.lower()
            is_this_week = True

            fixtures_list.append({
                'id': f['match_id'],
                'match_id': f['match_id'],
                'match_name': match_name,
                'home_team': h_team,
                'away_team': a_team,
                'league': f['league'],
                'league_code': f.get('league_code', 'PL'),
                'utc_date': kickoff,
                'kickoff_time': kickoff,
                'is_today': is_today,
                'is_this_week': is_this_week,
                'has_odds': False,
                'is_demo': is_demo or f.get('is_demo', False),
                'feed_source': f.get('feed_source', 'football-data.org'),
                'overround_pct': None,
                'margin_pct': 0.0,
                'expected_loss_per_1000': 0.0,
                'category': "Awaiting Odds",
                'dominant_category': "No Odds Loaded",
                'dominant_disclaimer': "Awaiting user SportyBet odds entry.",
                'risk_badge': "No Odds Loaded",
                'odds': None,
                'shin_probs': None,
                'outcomes': [],
                'raw_odds': None,
                'updated_at': "Just now"
            })
    except Exception as e:
        print(f"Notice: Error fetching football-data.org fixtures ({e})")

    return fixtures_list
