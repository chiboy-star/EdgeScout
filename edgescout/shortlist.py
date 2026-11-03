"""
Suggestion Shortlist Engine for EdgeScout Phase 4.3.
Selects and ranks candidate betting opportunities based on LOWEST EXPECTED COST,
multi-bookmaker line shopping, Shin de-vigged consensus probability,
supporting facts (Form, H2H, Rest days, Form/Market agreement flag),
and 15-season empirical historical ROI for that league/odds bucket.

Core Rule: Never predict profit or winners.
Every pick is labeled: "Lowest-cost pick, not a prediction of profit."

Tiers (Max 3 per tier):
1. Steady: consensus market prob >= 55%
2. Balanced: consensus market prob 35-55%
3. Long shot: consensus market prob < 20% (hard stake cap 0.25% of bankroll)
"""
import time
import sqlite3
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime, timezone, timedelta

from edgescout.config import DEFAULT_DB_PATH, CACHE_DIR
from edgescout.models.margin import remove_margin_shin, calculate_overround
from edgescout.backtest.metrics import bootstrap_ci
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

LEAGUE_DIV_MAP = {
    'E0': 'Premier League',
    'E1': 'Championship',
    'SP1': 'La Liga',
    'I1': 'Serie A',
    'D1': 'Bundesliga',
    'F1': 'Ligue 1',
    'B1': 'Belgian First Division',
    'N1': 'Dutch Eredivisie',
    'P1': 'Portuguese Primeira Liga'
}

# Bookmaker prefixes in fixtures.csv
BOOKMAKER_MAP = [
    ('B365', 'Bet365'),
    ('BV', 'BetVictor'),
    ('BW', 'Bwin'),
    ('SKB', 'SkyBet'),
    ('PP', 'PaddyPower'),
    ('BFD', 'Betfair'),
    ('PS', 'Pinnacle'),
]

_ODDS_BUCKET_CACHE: Dict[str, Dict[str, Any]] = {}


def get_team_recent_form(conn: sqlite3.Connection, team_name: str, n: int = 5) -> Dict[str, Any]:
    """Extracts last N match results for team from SQLite database."""
    query = """
    SELECT match_date, home_team, away_team, ftr
    FROM matches
    WHERE (home_team = ? OR away_team = ?) AND ftr IN ('H', 'D', 'A')
    ORDER BY match_date DESC
    LIMIT ?;
    """
    cur = conn.cursor()
    cur.execute(query, (team_name, team_name, n))
    rows = cur.fetchall()

    if not rows:
        return {'record': ['D', 'D', 'D'], 'points': 3, 'last_match_date': None, 'limited_history': True}

    results = []
    points = 0
    last_date = rows[0][0]

    for m_date, h_team, a_team, ftr in rows:
        if h_team == team_name:
            if ftr == 'H':
                results.append('W'); points += 3
            elif ftr == 'D':
                results.append('D'); points += 1
            else:
                results.append('L')
        else:
            if ftr == 'A':
                results.append('W'); points += 3
            elif ftr == 'D':
                results.append('D'); points += 1
            else:
                results.append('L')

    return {
        'record': results,
        'points': points,
        'last_match_date': last_date,
        'limited_history': len(rows) < 5
    }


def get_head_to_head(conn: sqlite3.Connection, home_team: str, away_team: str, n: int = 5) -> Dict[str, int]:
    """Extracts head-to-head record from historical database."""
    query = """
    SELECT home_team, away_team, ftr
    FROM matches
    WHERE ((home_team = ? AND away_team = ?) OR (home_team = ? AND away_team = ?))
      AND ftr IN ('H', 'D', 'A')
    ORDER BY match_date DESC
    LIMIT ?;
    """
    cur = conn.cursor()
    cur.execute(query, (home_team, away_team, away_team, home_team, n))
    rows = cur.fetchall()

    h_wins, draws, a_wins = 0, 0, 0
    for h, a, ftr in rows:
        if h == home_team:
            if ftr == 'H': h_wins += 1
            elif ftr == 'D': draws += 1
            else: a_wins += 1
        else:
            if ftr == 'A': h_wins += 1
            elif ftr == 'D': draws += 1
            else: a_wins += 1

    return {'home_wins': h_wins, 'draws': draws, 'away_wins': a_wins, 'total': len(rows)}


def get_odds_bucket_stats(
    conn: sqlite3.Connection,
    league_code: str,
    selection: str,
    odds: float
) -> Dict[str, Any]:
    """Extracts 15-season empirical ROI and 95% Bootstrap CI for odds bucket."""
    if odds < 1.50:
        bucket_label = "Heavy Favourite (< 1.50)"
        odds_min, odds_max = 1.01, 1.50
    elif odds < 2.00:
        bucket_label = "Moderate Favourite (1.50 - 2.00)"
        odds_min, odds_max = 1.50, 2.00
    elif odds < 3.00:
        bucket_label = "Contested (2.00 - 3.00)"
        odds_min, odds_max = 2.00, 3.00
    elif odds < 5.00:
        bucket_label = "Underdog (3.00 - 5.00)"
        odds_min, odds_max = 3.00, 5.00
    else:
        bucket_label = "Longshot (> 5.00)"
        odds_min, odds_max = 5.00, 50.0

    cache_key = f"{league_code}_{selection}_{odds_min}_{odds_max}"
    if cache_key in _ODDS_BUCKET_CACHE:
        return _ODDS_BUCKET_CACHE[cache_key]

    odd_col = 'b365_h' if selection == 'H' else ('b365_d' if selection == 'D' else 'b365_a')
    query = f"""
    SELECT m.ftr, o.{odd_col}
    FROM matches m
    JOIN odds o ON m.match_id = o.match_id
    WHERE m.league_code = ? AND o.{odd_col} >= ? AND o.{odd_col} < ? AND m.ftr IS NOT NULL;
    """
    cur = conn.cursor()
    cur.execute(query, (league_code, odds_min, odds_max))
    rows = cur.fetchall()

    if len(rows) < 30:
        # Fallback to pooled across leagues
        query_all = f"""
        SELECT m.ftr, o.{odd_col}
        FROM matches m
        JOIN odds o ON m.match_id = o.match_id
        WHERE o.{odd_col} >= ? AND o.{odd_col} < ? AND m.ftr IS NOT NULL;
        """
        cur.execute(query_all, (odds_min, odds_max))
        rows = cur.fetchall()

    if not rows:
        res = {
            'bucket_label': bucket_label,
            'historical_bets': 0,
            'historical_roi_pct': -5.0,
            'roi_ci': (-5.0, -8.0, -2.0),
            'hit_rate_pct': 0.0
        }
        _ODDS_BUCKET_CACHE[cache_key] = res
        return res

    returns = []
    wins = 0
    for ftr, o_val in rows:
        if o_val and o_val > 1.0:
            won = (ftr == selection)
            returns.append((o_val - 1.0) if won else -1.0)
            if won: wins += 1

    n_bets = len(returns)
    roi_pct = (sum(returns) / n_bets) * 100.0 if n_bets > 0 else 0.0
    hit_rate = (wins / n_bets) * 100.0 if n_bets > 0 else 0.0
    roi_pt, ci_lo, ci_hi = bootstrap_ci(np.array(returns))

    res = {
        'bucket_label': bucket_label,
        'historical_bets': n_bets,
        'historical_roi_pct': round(roi_pct, 2),
        'roi_ci': (round(roi_pt, 2), round(ci_lo, 2), round(ci_hi, 2)),
        'hit_rate_pct': round(hit_rate, 1)
    }
    _ODDS_BUCKET_CACHE[cache_key] = res
    return res


def compute_line_shopping_and_consensus(row: pd.Series) -> Optional[Dict[str, Any]]:
    """
    Extracts odds across available bookmakers, computes Shin consensus probability
    (weighting Pinnacle 3x when present), and line shopping comparisons.
    """
    bookmaker_odds = {}
    fair_probs_list = []
    weights_list = []
    margins_list = []

    for prefix, b_name in BOOKMAKER_MAP:
        try:
            h = float(row.get(f'{prefix}H', 0))
            d = float(row.get(f'{prefix}D', 0))
            a = float(row.get(f'{prefix}A', 0))
            if h > 1.0 and d > 1.0 and a > 1.0:
                bookmaker_odds[b_name] = {'H': h, 'D': d, 'A': a}
                m = calculate_overround([h, d, a])
                margins_list.append(m * 100.0)
                fp, _ = remove_margin_shin([h, d, a])
                fair_probs_list.append(fp)
                # Pinnacle weighted 3x, others 1x
                w = 3.0 if prefix == 'PS' else 1.0
                weights_list.append(w)
        except (ValueError, TypeError):
            continue

    if not fair_probs_list:
        return None

    # Weighted consensus probability
    total_w = sum(weights_list)
    consensus_probs = [
        sum(fair_probs_list[j][i] * weights_list[j] for j in range(len(fair_probs_list))) / total_w
        for i in range(3)
    ]
    # Normalize
    s_prob = sum(consensus_probs)
    consensus_probs = [p / s_prob for p in consensus_probs]

    avg_margin_pct = sum(margins_list) / len(margins_list) if margins_list else 5.0

    return {
        'bookmaker_odds': bookmaker_odds,
        'consensus_probs': consensus_probs,
        'consensus_margin_pct': round(avg_margin_pct, 2)
    }


def generate_suggestion_shortlist(
    db_path: str = str(DEFAULT_DB_PATH),
    bankroll: float = 100000.0,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Generates ranked shortlist across 3 tiers (max 3 per tier):
    - Steady: consensus prob >= 55%
    - Balanced: consensus prob 35% - 55%
    - Long shot: consensus prob < 20% (hard stake cap 0.25% of bankroll)
    Enforces DATE INTEGRITY: never includes matches kicking off in < 10 mins or in the past.
    """
    df_raw = load_fixtures_dataframe(force_refresh=force_refresh)
    conn = sqlite3.connect(db_path)
    now_utc = get_now_utc()
    health_stats = get_data_health_stats(Path(db_path))

    candidates = []
    scanned_count = 0
    skipped_breakdown = {
        'past_or_soon': 0,
        'high_margin': 0,
        'outside_tiers': 0,
        'missing_odds': 0,
        'tier_capped': 0
    }
    per_day_summary: Dict[str, Dict[str, int]] = {}

    if not df_raw.empty and 'HomeTeam' in df_raw.columns and 'Date' in df_raw.columns:
        for idx, row in df_raw.iterrows():
            scanned_count += 1
            raw_date = str(row.get('Date', ''))
            raw_time = str(row.get('Time', ''))
            dt_utc = parse_kickoff_to_utc(raw_date, raw_time)

            if not dt_utc:
                skipped_breakdown['missing_odds'] += 1
                continue

            # Day key for daily breakdown
            day_label = dt_utc.strftime('%Y-%m-%d')
            if day_label not in per_day_summary:
                per_day_summary[day_label] = {'scanned': 0, 'qualified': 0}
            per_day_summary[day_label]['scanned'] += 1

            # Strict Date Integrity check
            is_today, is_this_week = is_upcoming_fixture(dt_utc, min_buffer_minutes=10, now_utc=now_utc)
            if not is_this_week:
                skipped_breakdown['past_or_soon'] += 1
                continue

            div = str(row.get('Div', 'E0'))
            if div not in LEAGUE_DIV_MAP:
                continue
            league_name = LEAGUE_DIV_MAP[div]
            home_team = str(row['HomeTeam'])
            away_team = str(row['AwayTeam'])

            # Multi-bookmaker line shopping & consensus
            market_data = compute_line_shopping_and_consensus(row)
            if not market_data:
                skipped_breakdown['missing_odds'] += 1
                continue

            consensus_probs = market_data['consensus_probs']
            margin_pct = market_data['consensus_margin_pct']
            b_odds = market_data['bookmaker_odds']

            # Vig filter: skip if consensus margin exceeds 6.0%
            if margin_pct > 6.0:
                skipped_breakdown['high_margin'] += 1
                continue

            # Team form & H2H from SQLite
            h_form = get_team_recent_form(conn, home_team, 5)
            a_form = get_team_recent_form(conn, away_team, 5)
            h2h = get_head_to_head(conn, home_team, away_team, 5)

            # Rest days computation
            rest_days_h = 7
            rest_days_a = 7
            if h_form.get('last_match_date'):
                try:
                    last_h = datetime.strptime(h_form['last_match_date'], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    rest_days_h = max(1, (dt_utc - last_h).days)
                except Exception: pass
            if a_form.get('last_match_date'):
                try:
                    last_a = datetime.strptime(a_form['last_match_date'], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    rest_days_a = max(1, (dt_utc - last_a).days)
                except Exception: pass

            selections = [
                ('H', f"{home_team} (Home)", 0, h_form['points']),
                ('D', "Draw", 1, 5),
                ('A', f"{away_team} (Away)", 2, a_form['points'])
            ]

            match_id = f"fix_{div}_{dt_utc.strftime('%Y%m%d')}_{idx}"
            kickoff_wat = format_wat(dt_utc)
            countdown = format_countdown(dt_utc, now_utc)

            for sel_code, sel_label, sel_idx, team_pts in selections:
                p_fair = consensus_probs[sel_idx]
                p_pct = p_fair * 100.0

                # Tier assignment
                if p_pct >= 55.0:
                    tier = "Steady"
                    stake_pct = 0.01
                    stake_cap = 0.02
                elif 35.0 <= p_pct < 55.0:
                    tier = "Balanced"
                    stake_pct = 0.01
                    stake_cap = 0.02
                elif p_pct < 20.0:
                    tier = "Long shot"
                    stake_pct = 0.0025 # 0.25% hard cap
                    stake_cap = 0.0025
                else:
                    skipped_breakdown['outside_tiers'] += 1
                    continue

                # Line Shopping: evaluate all bookmakers offering this selection
                quotes = {}
                for b_name, odds_dict in b_odds.items():
                    if sel_code in odds_dict and odds_dict[sel_code] > 1.0:
                        quotes[b_name] = odds_dict[sel_code]

                if not quotes:
                    continue

                b365_odd = quotes.get('Bet365', list(quotes.values())[0])
                best_bookmaker, best_odd = max(quotes.items(), key=lambda x: x[1])

                # Expected costs per 1,000 staked
                cost_best_1000 = max(0.0, 1000.0 * (1.0 - (p_fair * best_odd)))
                cost_b365_1000 = max(0.0, 1000.0 * (1.0 - (p_fair * b365_odd)))
                savings_1000 = max(0.0, cost_b365_1000 - cost_best_1000)

                # Supporting facts score
                facts_score = team_pts * 2.0 - (margin_pct * 1.5)
                if sel_code == 'H':
                    facts_score += h2h['home_wins'] * 2.5
                elif sel_code == 'A':
                    facts_score += h2h['away_wins'] * 2.5

                # Agreement Flag between form and market
                if p_pct >= 55.0:
                    agreement_flag = "Form confirms market favouritism" if team_pts >= 8 else "Form diverges: team stumbling despite short market price"
                elif p_pct >= 35.0:
                    agreement_flag = "Evenly matched: recent form reflects contested market line"
                else:
                    agreement_flag = "Form diverges: underdog showing resilient form" if team_pts >= 7 else "Form confirms longshot status"

                # One-line explanation: Why this is listed
                why_listed = f"Lowest expected friction in {tier} ({margin_pct:.1f}% vig); {best_bookmaker} offers best price @ {best_odd:.2f} (saves ₦{savings_1000:.1f}/1k vs Bet365)."

                # Historical bucket result from 15 seasons
                hist_stats = get_odds_bucket_stats(conn, div, sel_code, best_odd)

                # Sizing rules: Stakes assigned ONLY for Today (< 24h)
                # This Week shows no stakes (odds may move)
                if is_today:
                    suggested_stake = min(round(bankroll * stake_pct, 2), round(bankroll * stake_cap, 2))
                else:
                    suggested_stake = None

                candidates.append({
                    'match_id': match_id,
                    'match_name': f"{home_team} vs {away_team}",
                    'home_team': home_team,
                    'away_team': away_team,
                    'league': league_name,
                    'league_code': div,
                    'kickoff_utc': dt_utc.isoformat(),
                    'kickoff_wat': kickoff_wat,
                    'kickoff_countdown': countdown,
                    'is_today': is_today,
                    'is_this_week': is_this_week,
                    'selection': sel_code,
                    'selection_label': sel_label,
                    'odds_taken': best_odd,
                    'best_bookmaker': best_bookmaker,
                    'b365_odds': b365_odd,
                    'shin_market_prob_pct': round(p_pct, 1),
                    'bookmaker_margin_pct': round(margin_pct, 2),
                    'expected_cost_per_1000': round(cost_best_1000, 2),
                    'expected_loss_pct': round((cost_best_1000 / 1000.0) * 100.0, 2),
                    'savings_per_1000_vs_b365': round(savings_1000, 2),
                    'line_shopping': {
                        'best_bookmaker': best_bookmaker,
                        'best_odds': best_odd,
                        'b365_odds': b365_odd,
                        'cost_best_1000': round(cost_best_1000, 2),
                        'cost_b365_1000': round(cost_b365_1000, 2),
                        'savings_1000': round(savings_1000, 2),
                        'quotes': quotes
                    },
                    'tier': tier,
                    'suggested_stake': suggested_stake,
                    'stake_cap_pct': round(stake_cap * 100.0, 2),
                    'supporting_facts': {
                        'home_form_last5': "-".join(h_form['record']),
                        'home_form_pts': h_form['points'],
                        'away_form_last5': "-".join(a_form['record']),
                        'away_form_pts': a_form['points'],
                        'h2h_last5': f"{h2h['home_wins']}W-{h2h['draws']}D-{h2h['away_wins']}L",
                        'rest_days_home': rest_days_h,
                        'rest_days_away': rest_days_a,
                        'agreement_flag': agreement_flag,
                        'facts_score': round(facts_score, 1)
                    },
                    'why_listed': why_listed,
                    'historical_bucket': hist_stats,
                    'limited_history': h_form.get('limited_history', False) or a_form.get('limited_history', False),
                    'history_badge': "Limited history" if (h_form.get('limited_history', False) or a_form.get('limited_history', False)) else "5-match sample",
                    'pick_label': "Lowest-cost pick, not a prediction of profit.",
                    'prefill': {
                        'match_name': f"{home_team} vs {away_team}",
                        'selection': sel_code,
                        'home_odds': b_odds.get(best_bookmaker, {}).get('H', best_odd),
                        'draw_odds': b_odds.get(best_bookmaker, {}).get('D', 3.30),
                        'away_odds': b_odds.get(best_bookmaker, {}).get('A', 3.40)
                    }
                })

                if day_label in per_day_summary:
                    per_day_summary[day_label]['qualified'] += 1

    conn.close()

    # Group into tiers and cap at top 3 by LOWEST expected cost
    tiers = {'Steady': [], 'Balanced': [], 'Long shot': []}
    for c in candidates:
        if c['tier'] in tiers:
            tiers[c['tier']].append(c)

    for t_name in tiers:
        tiers[t_name].sort(key=lambda x: (x['expected_cost_per_1000'], -x['supporting_facts']['facts_score']))
        if len(tiers[t_name]) > 3:
            skipped_breakdown['tier_capped'] += (len(tiers[t_name]) - 3)
            tiers[t_name] = tiers[t_name][:3]

    total_qual = sum(len(v) for v in tiers.values())

    return {
        'tiers': tiers,
        'summary': {
            'steady_count': len(tiers['Steady']),
            'balanced_count': len(tiers['Balanced']),
            'long_shot_count': len(tiers['Long shot']),
            'total_shortlisted': total_qual,
            'max_per_tier': 3,
            'bankroll': bankroll,
            'label': "Lowest-cost pick, not a prediction of profit."
        },
        'scan_summary': {
            'fixtures_scanned': scanned_count,
            'fixtures_qualified': total_qual,
            'skipped_breakdown': skipped_breakdown,
            'per_day': per_day_summary
        },
        'data_health': health_stats
    }
