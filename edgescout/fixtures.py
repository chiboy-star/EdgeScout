"""
Fixtures & Market View Engine for EdgeScout Phase 4.3.
Integrates with football-data.co.uk pre-match odds and scheduled feed.
Enforces DATE INTEGRITY:
- Kickoff parsed from UK local time (Europe/London) and stored in UTC.
- Displayed in Africa/Lagos (WAT, UTC+1) as "Tue 3 Nov, 19:45 WAT" plus "in 3h 20m".
- Never displays matches in the past or kicking off in < 10 mins.
- Provides margin %, Shin de-vigged fair probabilities, and expected loss per 1,000 staked.
"""
import sqlite3
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
from pathlib import Path

from edgescout.config import DEFAULT_DB_PATH
from edgescout.models.margin import remove_margin_shin, calculate_overround
from edgescout.dates import (
    parse_kickoff_to_utc,
    format_wat,
    format_countdown,
    is_upcoming_fixture,
    get_now_utc
)
from edgescout.data.fixtures_feed import (
    load_fixtures_dataframe,
    get_data_health_stats,
    FIXTURES_CACHE_FILE
)
from edgescout.shortlist import (
    LEAGUE_DIV_MAP,
    BOOKMAKER_MAP,
    compute_line_shopping_and_consensus
)


def get_risk_badge(overround_pct: Optional[float], min_odds: Optional[float], max_odds: Optional[float]) -> str:
    """Computes concise risk badge string for display."""
    if overround_pct is None:
        return "No Odds Loaded"
    if overround_pct > 6.0:
        return f"High Vig ({overround_pct:.1f}%)"
    if overround_pct > 4.5:
        return f"Standard Vig ({overround_pct:.1f}%)"
    return f"Competitive Vig ({overround_pct:.1f}%)"


def get_market_fixtures(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Returns today and this week market fixtures with odds.
    Strictly filters out any fixture whose kickoff is before now + 10 minutes.
    Sorts upcoming fixtures by earliest kickoff ascending.
    """
    df = load_fixtures_dataframe(force_refresh=force_refresh)
    now_utc = get_now_utc()
    fixtures_list = []
    seen_match_keys = set()

    if not df.empty and 'HomeTeam' in df.columns and 'Date' in df.columns:
        for idx, row in df.iterrows():
            raw_date = str(row.get('Date', ''))
            raw_time = str(row.get('Time', ''))
            dt_utc = parse_kickoff_to_utc(raw_date, raw_time)

            if not dt_utc:
                continue

            # Strict Date Integrity: Exclude past matches or matches kicking off in < 10 mins
            is_today, is_this_week = is_upcoming_fixture(dt_utc, min_buffer_minutes=10, now_utc=now_utc)
            if not is_this_week:
                continue

            div = str(row.get('Div', 'E0'))
            if div not in LEAGUE_DIV_MAP:
                continue
            league_name = LEAGUE_DIV_MAP[div]
            h_team = str(row['HomeTeam'])
            a_team = str(row['AwayTeam'])
            match_key = f"{h_team}_{a_team}_{dt_utc.strftime('%Y%m%d%H%M')}"
            if match_key in seen_match_keys:
                continue
            seen_match_keys.add(match_key)

            match_name = f"{h_team} vs {a_team}"
            kickoff_wat = format_wat(dt_utc)
            countdown = format_countdown(dt_utc, now_utc)

            # Compute line shopping and multi-bookmaker consensus
            market_data = compute_line_shopping_and_consensus(row)

            if market_data:
                consensus_probs = market_data['consensus_probs']
                margin_pct = market_data['consensus_margin_pct']
                b_odds = market_data['bookmaker_odds']

                # Extract best quotes
                best_h_book, best_h = max(((b, odds['H']) for b, odds in b_odds.items() if 'H' in odds), key=lambda x: x[1], default=('Bet365', 2.0))
                best_d_book, best_d = max(((b, odds['D']) for b, odds in b_odds.items() if 'D' in odds), key=lambda x: x[1], default=('Bet365', 3.2))
                best_a_book, best_a = max(((b, odds['A']) for b, odds in b_odds.items() if 'A' in odds), key=lambda x: x[1], default=('Bet365', 3.4))

                b365_odds = b_odds.get('Bet365', {'H': best_h, 'D': best_d, 'A': best_a})
                h_odd = b365_odds.get('H', best_h)
                d_odd = b365_odds.get('D', best_d)
                a_odd = b365_odds.get('A', best_a)

                max_p = max(consensus_probs)
                if max_p >= 0.65:
                    category = "Market Favourite"
                elif max_p >= 0.35:
                    category = "Contested"
                elif max_p < 0.20:
                    category = "Longshot"
                else:
                    category = "Contested"

                dominant_cat = f"{category} (max prob {round(max_p * 100, 1)}%)"
                # Cost per 1k on favourite
                fav_idx = consensus_probs.index(max_p)
                fav_odd = [h_odd, d_odd, a_odd][fav_idx]
                expected_loss_1000 = round(max(0.0, 1000.0 * (1.0 - (max_p * fav_odd))), 2)

                odds_obj = {
                    'home': h_odd,
                    'draw': d_odd,
                    'away': a_odd,
                    'source': "Bet365-reference (Line shopping available)",
                    'best_home': best_h,
                    'best_home_book': best_h_book,
                    'best_draw': best_d,
                    'best_draw_book': best_d_book,
                    'best_away': best_a,
                    'best_away_book': best_a_book
                }

                shin_probs_obj = {
                    'home_pct': round(consensus_probs[0] * 100, 1),
                    'draw_pct': round(consensus_probs[1] * 100, 1),
                    'away_pct': round(consensus_probs[2] * 100, 1)
                }

                has_odds = True
                risk_badge = get_risk_badge(margin_pct, min(h_odd, a_odd), max(h_odd, a_odd))
            else:
                has_odds = False
                margin_pct = 0.0
                expected_loss_1000 = 0.0
                category = "Awaiting Odds"
                dominant_cat = "Awaiting SportyBet odds entry"
                risk_badge = "No Odds Loaded"
                odds_obj = None
                shin_probs_obj = None

            fixtures_list.append({
                'id': f"fix_{div}_{dt_utc.strftime('%Y%m%d%H%M')}_{idx}",
                'match_name': match_name,
                'home_team': h_team,
                'away_team': a_team,
                'league': league_name,
                'league_code': div,
                'kickoff_utc': dt_utc.isoformat(),
                'kickoff_wat': kickoff_wat,
                'kickoff_countdown': countdown,
                'utc_date': f"{kickoff_wat} ({countdown})",
                'is_today': is_today,
                'is_this_week': is_this_week,
                'has_odds': has_odds,
                'odds': odds_obj,
                'shin_probs': shin_probs_obj,
                'margin_pct': margin_pct,
                'expected_loss_per_1000': expected_loss_1000,
                'category': category,
                'dominant_category': dominant_cat,
                'risk_badge': risk_badge,
                'is_demo': False,
                'feed_source': "football-data.co.uk / SportyBet"
            })

    # Sort strictly by kickoff time ascending (earliest upcoming match first)
    fixtures_list.sort(key=lambda f: f['kickoff_utc'])
    return fixtures_list
