"""
Fixtures & Market View Engine for EdgeScout Phase 4.4.
Enforces 100% REAL DATA from verified sources:
- football-data.co.uk fixtures.csv (real multi-bookmaker odds)
- api.football-data.org (real Tier One schedules: Champions League, Premier League, etc.)
- SQLite custom_fixtures (user manual entries)

Strict rules:
1. Every fixture carries an explicit, non-empty `source` tag.
2. Any fixture lacking an auditable source is rejected.
3. Zero hardcoded mock slates.
4. Date integrity: kickoffs parsed to UTC, displayed in Africa/Lagos (WAT),
   fixtures with kickoff < now + 10m are strictly excluded.
"""
import re
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
    fetch_football_data_co_uk_csv,
    fetch_football_data_org_matches,
    get_custom_fixtures,
    get_data_health_stats,
    LEAGUE_DIV_MAP,
    FD_ORG_COMP_MAP
)

# Multi-bookmaker prefixes
BOOKMAKER_MAP = [
    ('B365', 'Bet365'),
    ('BV', 'BetVictor'),
    ('BW', 'Bwin'),
    ('SKB', 'SkyBet'),
    ('PP', 'PaddyPower'),
    ('BFD', 'Betfair'),
    ('PS', 'Pinnacle'),
]


def normalize_team_name(name: str) -> str:
    """Normalizes team name for matching across feeds."""
    n = name.lower()
    n = re.sub(r'\b(fc|afc|cf|sc|sk|fk|ac|as|sv|vfb|kv)\b', '', n)
    n = re.sub(r'[^a-z0-9]', '', n)
    return n.strip()


def get_risk_badge(overround_pct: Optional[float], min_odds: Optional[float], max_odds: Optional[float]) -> str:
    """Computes concise risk badge string for display."""
    if overround_pct is None:
        return "No Odds Loaded"
    if overround_pct > 6.0:
        return f"High Vig ({overround_pct:.1f}%)"
    if overround_pct > 4.5:
        return f"Standard Vig ({overround_pct:.1f}%)"
    return f"Competitive Vig ({overround_pct:.1f}%)"


def extract_bookmaker_quotes(row: Any) -> Dict[str, Dict[str, float]]:
    """Extracts all valid decimal odds per bookmaker from a fixtures row."""
    b_odds = {}
    for prefix, b_name in BOOKMAKER_MAP:
        try:
            h = float(row.get(f"{prefix}H", 0) or 0)
            d = float(row.get(f"{prefix}D", 0) or 0)
            a = float(row.get(f"{prefix}A", 0) or 0)
            if h > 1.0 and d > 1.0 and a > 1.0:
                b_odds[b_name] = {'H': h, 'D': d, 'A': a}
        except (ValueError, TypeError):
            continue
    return b_odds


def compute_market_consensus(b_odds: Dict[str, Dict[str, float]]) -> Optional[Dict[str, Any]]:
    """Computes Shin de-vigged market consensus across bookmakers."""
    if not b_odds:
        return None

    probs_list = []
    weights = []
    margins = []

    for b_name, odds in b_odds.items():
        h, d, a = odds['H'], odds['D'], odds['A']
        raw_m = calculate_overround([h, d, a])
        p_fair, _ = remove_margin_shin([h, d, a])
        w = 3.0 if b_name == 'Pinnacle' else 1.0
        probs_list.append(p_fair)
        weights.append(w)
        margins.append(raw_m * 100.0)

    total_w = sum(weights)
    consensus_probs = [
        sum(probs_list[i][k] * weights[i] for i in range(len(probs_list))) / total_w
        for k in range(3)
    ]
    sum_p = sum(consensus_probs)
    consensus_probs = [p / sum_p for p in consensus_probs]
    avg_margin = sum(margins[i] * weights[i] for i in range(len(margins))) / total_w

    return {
        'consensus_probs': consensus_probs,
        'consensus_margin_pct': avg_margin,
        'bookmaker_odds': b_odds
    }


def get_market_fixtures(force_refresh: bool = False, db_path: Path = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """
    Returns unified list of upcoming fixtures from verified real sources:
    1. football-data.co.uk fixtures.csv (real bookmaker odds)
    2. football-data.org (Tier One schedules: Champions League, Premier League, etc.)
    3. SQLite custom_fixtures (manual user entries)

    Strictly excludes fixtures where kickoff_utc < now_utc + 10m.
    Every fixture carries a verified, non-empty source tag.
    """
    now_utc = get_now_utc()
    fixtures_list = []
    seen_match_keys = set()

    # 1. Load football-data.co.uk fixtures.csv
    df_csv, csv_fetch_time = fetch_football_data_co_uk_csv()
    csv_matches_by_key = {}

    if not df_csv.empty and 'HomeTeam' in df_csv.columns and 'Date' in df_csv.columns:
        for idx, row in df_csv.iterrows():
            raw_date = str(row.get('Date', ''))
            raw_time = str(row.get('Time', ''))
            dt_utc = parse_kickoff_to_utc(raw_date, raw_time)
            if not dt_utc:
                continue

            # Strict date integrity: exclude past matches or matches kicking off in < 10 mins
            is_today, is_this_week = is_upcoming_fixture(dt_utc, min_buffer_minutes=10, now_utc=now_utc)
            if not is_this_week:
                continue

            div = str(row.get('Div', 'E1'))
            league_name = LEAGUE_DIV_MAP.get(div, div)
            h_team = str(row['HomeTeam']).strip()
            a_team = str(row['AwayTeam']).strip()
            norm_key = f"{normalize_team_name(h_team)}_{normalize_team_name(a_team)}"
            match_name = f"{h_team} vs {a_team}"
            kickoff_wat = format_wat(dt_utc)
            countdown = format_countdown(dt_utc, now_utc)

            # Extract bookmaker quotes & consensus
            b_odds = extract_bookmaker_quotes(row)
            market_data = compute_market_consensus(b_odds)

            if market_data:
                consensus_probs = market_data['consensus_probs']
                margin_pct = market_data['consensus_margin_pct']
                b_odds_dict = market_data['bookmaker_odds']

                best_h_book, best_h = max(((b, odds['H']) for b, odds in b_odds_dict.items() if 'H' in odds), key=lambda x: x[1], default=('Bet365', 2.0))
                best_d_book, best_d = max(((b, odds['D']) for b, odds in b_odds_dict.items() if 'D' in odds), key=lambda x: x[1], default=('Bet365', 3.2))
                best_a_book, best_a = max(((b, odds['A']) for b, odds in b_odds_dict.items() if 'A' in odds), key=lambda x: x[1], default=('Bet365', 3.4))

                b365_odds = b_odds_dict.get('Bet365', {'H': best_h, 'D': best_d, 'A': best_a})
                h_odd = b365_odds.get('H', best_h)
                d_odd = b365_odds.get('D', best_d)
                a_odd = b365_odds.get('A', best_a)

                max_p = max(consensus_probs)
                if max_p >= 0.65: category = "Market Favourite"
                elif max_p >= 0.35: category = "Contested"
                else: category = "Longshot"

                dominant_cat = f"{category} (max prob {round(max_p * 100, 1)}%)"
                fav_idx = consensus_probs.index(max_p)
                fav_odd = [h_odd, d_odd, a_odd][fav_idx]
                expected_loss_1000 = round(max(0.0, 1000.0 * (1.0 - (max_p * fav_odd))), 2)

                odds_obj = {
                    'home': h_odd,
                    'draw': d_odd,
                    'away': a_odd,
                    'source': "fixtures.csv (multi-bookmaker line shopping)",
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

            source_tag = f"football-data.co.uk fixtures.csv (fetched {csv_fetch_time})"

            fix_record = {
                'id': f"fix_csv_{div}_{dt_utc.strftime('%Y%m%d%H%M')}_{idx}",
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
                'source': source_tag,
                'feed_source': source_tag,
                'is_demo': False
            }
            fixtures_list.append(fix_record)
            seen_match_keys.add(norm_key)
            csv_matches_by_key[norm_key] = fix_record

    # 2. Load football-data.org matches (Champions League, Premier League, etc.)
    fd_matches, fd_fetch_time = fetch_football_data_org_matches()
    for m in fd_matches:
        try:
            utc_str = m.get('utcDate')
            if not utc_str:
                continue
            clean_utc = utc_str.replace("Z", "+00:00")
            dt_utc = datetime.fromisoformat(clean_utc)
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)

            is_today, is_this_week = is_upcoming_fixture(dt_utc, min_buffer_minutes=10, now_utc=now_utc)
            if not is_this_week:
                continue

            h_team = m.get('homeTeam', {}).get('name', 'Home')
            a_team = m.get('awayTeam', {}).get('name', 'Away')
            norm_key = f"{normalize_team_name(h_team)}_{normalize_team_name(a_team)}"

            # If already added via fixtures.csv, avoid duplicate
            if norm_key in seen_match_keys:
                continue
            seen_match_keys.add(norm_key)

            comp_code = m.get('competition', {}).get('code', 'CL')
            comp_name = m.get('competition', {}).get('name', 'UEFA Champions League')
            div_code, div_league = FD_ORG_COMP_MAP.get(comp_code, (comp_code, comp_name))

            kickoff_wat = format_wat(dt_utc)
            countdown = format_countdown(dt_utc, now_utc)
            source_tag = f"football-data.org API ({comp_name}, fetched {fd_fetch_time})"

            fixtures_list.append({
                'id': f"fix_fd_{m.get('id', int(dt_utc.timestamp()))}",
                'match_name': f"{h_team} vs {a_team}",
                'home_team': h_team,
                'away_team': a_team,
                'league': div_league,
                'league_code': div_code,
                'kickoff_utc': dt_utc.isoformat(),
                'kickoff_wat': kickoff_wat,
                'kickoff_countdown': countdown,
                'utc_date': f"{kickoff_wat} ({countdown})",
                'is_today': is_today,
                'is_this_week': is_this_week,
                'has_odds': False,
                'odds': None,
                'shin_probs': None,
                'margin_pct': 0.0,
                'expected_loss_per_1000': 0.0,
                'category': "Awaiting Odds",
                'dominant_category': "Awaiting SportyBet odds entry",
                'risk_badge': "No Odds Loaded",
                'source': source_tag,
                'feed_source': source_tag,
                'is_demo': False
            })
        except Exception:
            continue

    # 3. Load user-added custom fixtures from SQLite
    custom_fixes = get_custom_fixtures(db_path)
    for cf in custom_fixes:
        try:
            dt_utc = datetime.fromisoformat(cf['kickoff_utc'].replace("Z", "+00:00"))
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)

            is_today, is_this_week = is_upcoming_fixture(dt_utc, min_buffer_minutes=10, now_utc=now_utc)
            if not is_this_week:
                continue

            h_odd = cf['home_odds']
            d_odd = cf['draw_odds']
            a_odd = cf['away_odds']
            p_fair, _ = remove_margin_shin([h_odd, d_odd, a_odd])
            margin = calculate_overround([h_odd, d_odd, a_odd]) * 100.0
            p_fair_list = p_fair.tolist()
            max_p = max(p_fair_list)
            fav_idx = p_fair_list.index(max_p)
            fav_odd = [h_odd, d_odd, a_odd][fav_idx]
            exp_loss = round(max(0.0, 1000.0 * (1.0 - (max_p * fav_odd))), 2)

            kickoff_wat = format_wat(dt_utc)
            countdown = format_countdown(dt_utc, now_utc)

            fixtures_list.append({
                'id': cf['id'],
                'match_name': cf['match_name'],
                'home_team': cf['home_team'],
                'away_team': cf['away_team'],
                'league': cf['league'],
                'league_code': cf['league_code'],
                'kickoff_utc': dt_utc.isoformat(),
                'kickoff_wat': kickoff_wat,
                'kickoff_countdown': countdown,
                'utc_date': f"{kickoff_wat} ({countdown})",
                'is_today': is_today,
                'is_this_week': is_this_week,
                'has_odds': True,
                'odds': {
                    'home': h_odd,
                    'draw': d_odd,
                    'away': a_odd,
                    'source': "Manual User Entry",
                    'best_home': h_odd,
                    'best_home_book': "User",
                    'best_draw': d_odd,
                    'best_draw_book': "User",
                    'best_away': a_odd,
                    'best_away_book': "User"
                },
                'shin_probs': {
                    'home_pct': round(p_fair[0] * 100, 1),
                    'draw_pct': round(p_fair[1] * 100, 1),
                    'away_pct': round(p_fair[2] * 100, 1)
                },
                'margin_pct': round(margin, 2),
                'expected_loss_per_1000': exp_loss,
                'category': "Market Favourite" if max_p >= 0.65 else ("Contested" if max_p >= 0.35 else "Longshot"),
                'dominant_category': "User Custom Fixture",
                'risk_badge': get_risk_badge(margin, min(h_odd, a_odd), max(h_odd, a_odd)),
                'source': "manual_entry",
                'feed_source': "manual_entry",
                'is_demo': False
            })
        except Exception:
            continue

    # Reject any fixture without a valid source
    fixtures_list = [f for f in fixtures_list if f.get('source')]

    # Sort strictly by kickoff ascending
    fixtures_list.sort(key=lambda x: x['kickoff_utc'])
    return fixtures_list
