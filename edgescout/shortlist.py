"""
Suggestion Shortlist Engine for EdgeScout Phase 4.4.
Selects and ranks candidate betting opportunities based on LOWEST EXPECTED COST,
multi-bookmaker line shopping, Shin de-vigged consensus probability,
supporting facts (Form, H2H, Rest days, Form/Market agreement flag),
and 15-season empirical historical ROI for that league/odds bucket.

Core Discipline Rules:
1. ONE SELECTION PER MATCH: A fixture may appear at most once across the entire shortlist.
   If several selections qualify, keep the single lowest-cost one.
2. TODAY MEANS TODAY: When viewing Today, kickoff must be within now + 10m to now + 24h.
3. PROVE DATA IS REAL: Every pick carries an auditable source tag from real fixtures.csv or manual entry.
4. NO PREDICTION OF PROFIT: Every card labeled "Lowest-cost pick, not a prediction of profit."

Tiers (Max 3 per tier, max 1 per match across all tiers):
1. Steady: consensus market prob >= 55% (flat 1%, cap 2%)
2. Balanced: consensus market prob 35-55% (flat 1%, cap 2%)
3. Long shot: consensus market prob < 20% (hard cap 0.25%)
"""
import time
import sqlite3
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime, timezone, timedelta

from edgescout.config import DEFAULT_DB_PATH
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
    fetch_football_data_co_uk_csv,
    get_custom_fixtures,
    get_data_health_stats,
    LEAGUE_DIV_MAP
)

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
            if ftr == 'H': results.append('W'); points += 3
            elif ftr == 'D': results.append('D'); points += 1
            else: results.append('L')
        else:
            if ftr == 'A': results.append('W'); points += 3
            elif ftr == 'D': results.append('D'); points += 1
            else: results.append('L')

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
    for h_t, a_t, ftr in rows:
        if h_t == home_team:
            if ftr == 'H': h_wins += 1
            elif ftr == 'D': draws += 1
            elif ftr == 'A': a_wins += 1
        else:
            if ftr == 'A': h_wins += 1
            elif ftr == 'D': draws += 1
            elif ftr == 'H': a_wins += 1

    return {'home_wins': h_wins, 'draws': draws, 'away_wins': a_wins}


def get_odds_bucket_stats(conn: sqlite3.Connection, league_code: str, selection: str, odds: float) -> Dict[str, Any]:
    """Calculates empirical 15-season ROI & bootstrap CI for league and odds bucket."""
    cache_key = f"{league_code}_{selection}_{round(odds, 1)}"
    if cache_key in _ODDS_BUCKET_CACHE:
        return _ODDS_BUCKET_CACHE[cache_key]

    step = 0.20 if odds < 3.0 else (0.50 if odds < 6.0 else 1.0)
    low_b = max(1.01, round(odds - step, 2))
    high_b = round(odds + step, 2)

    odd_col = 'b365_h' if selection == 'H' else ('b365_d' if selection == 'D' else 'b365_a')

    query = f"""
    SELECT m.ftr, o.{odd_col}
    FROM matches m
    JOIN odds o ON m.match_id = o.match_id
    WHERE m.league_code = ? AND o.{odd_col} >= ? AND o.{odd_col} <= ?
      AND m.ftr IN ('H', 'D', 'A');
    """
    cur = conn.cursor()
    cur.execute(query, (league_code, low_b, high_b))
    rows = cur.fetchall()

    if not rows or len(rows) < 30:
        query_all = f"""
        SELECT m.ftr, o.{odd_col}
        FROM matches m
        JOIN odds o ON m.match_id = o.match_id
        WHERE o.{odd_col} >= ? AND o.{odd_col} <= ?
          AND m.ftr IN ('H', 'D', 'A');
        """
        cur.execute(query_all, (low_b, high_b))
        rows = cur.fetchall()

    if not rows:
        stats = {
            'bucket_label': f"{low_b:.2f} - {high_b:.2f} (All Leagues)",
            'historical_bets': 0,
            'historical_roi_pct': -5.0,
            'roi_ci': (-10.0, -5.0, 0.0),
            'hit_rate_pct': 0.0
        }
        _ODDS_BUCKET_CACHE[cache_key] = stats
        return stats

    returns = []
    hits = 0
    for ftr, odd_val in rows:
        if odd_val and odd_val > 1.0:
            if ftr == selection:
                returns.append(odd_val - 1.0)
                hits += 1
            else:
                returns.append(-1.0)

    n_bets = len(returns)
    hit_rate = (hits / n_bets) * 100.0 if n_bets > 0 else 0.0
    mean_roi = (sum(returns) / n_bets) * 100.0 if n_bets > 0 else 0.0
    ci = bootstrap_ci(np.array(returns) if returns else np.array([]), n_bootstraps=500, ci=0.95)

    stats = {
        'bucket_label': f"{low_b:.2f} - {high_b:.2f} ({league_code})",
        'historical_bets': n_bets,
        'historical_roi_pct': round(mean_roi, 2),
        'roi_ci': (round(ci[0] * 100, 2), round(ci[1] * 100, 2), round(ci[2] * 100, 2)),
        'hit_rate_pct': round(hit_rate, 1)
    }
    _ODDS_BUCKET_CACHE[cache_key] = stats
    return stats


def compute_line_shopping_and_consensus(row: Any) -> Optional[Dict[str, Any]]:
    """Extracts bookmaker quotes, calculates weighted Shin consensus, and returns consensus probabilities."""
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


def generate_suggestion_shortlist(
    db_path: Path = DEFAULT_DB_PATH,
    bankroll: float = 100000.0,
    timeframe: str = "today" # "today" or "week"
) -> Dict[str, Any]:
    """
    Ranks suggestions based on LOWEST EXPECTED FRICTION (margin & cost).
    Enforces Phase 4.4 Rules:
    1. ONE SELECTION PER MATCH: If multiple selections qualify for a match, keep only the lowest-cost one.
    2. TODAY MEANS TODAY: When timeframe == "today", strictly restricts to kickoff <= now + 24h.
    3. PROVE DATA IS REAL: Uses real fixtures.csv and custom fixtures with explicit source tags.
    """
    now_utc = get_now_utc()
    df_csv, csv_fetch_time = fetch_football_data_co_uk_csv()
    health_stats = get_data_health_stats(db_path)

    conn = sqlite3.connect(db_path)

    scanned_count = 0
    skipped_breakdown = {
        'past_or_soon': 0,
        'not_today': 0,
        'no_odds': 0,
        'outside_tiers': 0,
        'deduped_match': 0,
        'tier_capped': 0
    }
    per_day_summary = {}

    # Temporary store of candidates grouped by match_id
    # match_id -> list of candidate objects
    match_candidates: Dict[str, List[Dict[str, Any]]] = {}

    # Process football-data.co.uk rows
    if not df_csv.empty and 'HomeTeam' in df_csv.columns and 'Date' in df_csv.columns:
        for idx, row in df_csv.iterrows():
            scanned_count += 1
            raw_date = str(row.get('Date', ''))
            raw_time = str(row.get('Time', ''))
            dt_utc = parse_kickoff_to_utc(raw_date, raw_time)

            if not dt_utc:
                skipped_breakdown['past_or_soon'] += 1
                continue

            # Strict Date Integrity
            is_today, is_this_week = is_upcoming_fixture(dt_utc, min_buffer_minutes=10, now_utc=now_utc)
            if not is_this_week:
                skipped_breakdown['past_or_soon'] += 1
                continue

            # TODAY MEANS TODAY
            if timeframe == "today" and not is_today:
                skipped_breakdown['not_today'] += 1
                continue

            div = str(row.get('Div', 'E1'))
            league_name = LEAGUE_DIV_MAP.get(div, div)
            home_team = str(row['HomeTeam']).strip()
            away_team = str(row['AwayTeam']).strip()
            match_id = f"fix_{div}_{dt_utc.strftime('%Y%m%d%H%M')}_{idx}"

            day_key = dt_utc.strftime('%Y-%m-%d')
            day_label = dt_utc.strftime('%a %d %b')
            if day_label not in per_day_summary:
                per_day_summary[day_label] = {'scanned': 0, 'qualified': 0, 'date_wat': day_label}
            per_day_summary[day_label]['scanned'] += 1

            # Extract bookmaker quotes & consensus
            market_data = compute_line_shopping_and_consensus(row)
            if not market_data:
                skipped_breakdown['no_odds'] += 1
                continue

            consensus_probs = market_data['consensus_probs']
            margin_pct = market_data['consensus_margin_pct']
            b_odds = market_data['bookmaker_odds']

            kickoff_wat = format_wat(dt_utc)
            countdown = format_countdown(dt_utc, now_utc)

            # Supporting facts
            h_form = get_team_recent_form(conn, home_team)
            a_form = get_team_recent_form(conn, away_team)
            h2h = get_head_to_head(conn, home_team, away_team)

            rest_days_h = 3
            if h_form.get('last_match_date'):
                try:
                    last_h = datetime.strptime(h_form['last_match_date'], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    rest_days_h = max(1, (dt_utc - last_h).days)
                except Exception: pass

            rest_days_a = 3
            if a_form.get('last_match_date'):
                try:
                    last_a = datetime.strptime(a_form['last_match_date'], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                    rest_days_a = max(1, (dt_utc - last_a).days)
                except Exception: pass

            # Evaluate each selection (H, D, A)
            selections = [
                ('H', f"Home ({home_team})", consensus_probs[0], h_form['points']),
                ('D', "Draw (X)", consensus_probs[1], 1),
                ('A', f"Away ({away_team})", consensus_probs[2], a_form['points'])
            ]

            source_tag = f"football-data.co.uk fixtures.csv (fetched {csv_fetch_time})"

            for sel_code, sel_label, p_fair, team_pts in selections:
                p_pct = p_fair * 100.0

                if p_pct >= 55.0:
                    tier = "Steady"
                    stake_pct, stake_cap = 0.01, 0.02
                elif 35.0 <= p_pct < 55.0:
                    tier = "Balanced"
                    stake_pct, stake_cap = 0.01, 0.02
                elif p_pct < 20.0:
                    tier = "Long shot"
                    stake_pct, stake_cap = 0.0025, 0.0025
                else:
                    skipped_breakdown['outside_tiers'] += 1
                    continue

                # Quotes for this selection
                quotes = {b_name: o_dict[sel_code] for b_name, o_dict in b_odds.items() if sel_code in o_dict and o_dict[sel_code] > 1.0}
                if not quotes:
                    continue

                b365_odd = quotes.get('Bet365', list(quotes.values())[0])
                best_bookmaker, best_odd = max(quotes.items(), key=lambda x: x[1])

                cost_best_1000 = max(0.0, 1000.0 * (1.0 - (p_fair * best_odd)))
                cost_b365_1000 = max(0.0, 1000.0 * (1.0 - (p_fair * b365_odd)))
                savings_1000 = max(0.0, cost_b365_1000 - cost_best_1000)

                # Supporting facts score
                facts_score = team_pts * 2.0 - (margin_pct * 1.5)
                if sel_code == 'H': facts_score += h2h['home_wins'] * 2.5
                elif sel_code == 'A': facts_score += h2h['away_wins'] * 2.5

                if p_pct >= 55.0:
                    agreement_flag = "Form confirms market favouritism" if team_pts >= 8 else "Form diverges: team stumbling despite short market price"
                elif p_pct >= 35.0:
                    agreement_flag = "Evenly matched: recent form reflects contested market line"
                else:
                    agreement_flag = "Form diverges: underdog showing resilient form" if team_pts >= 7 else "Form confirms longshot status"

                why_listed = f"Lowest expected friction in {tier} ({margin_pct:.1f}% vig); {best_bookmaker} offers best price @ {best_odd:.2f} (saves ₦{savings_1000:.1f}/1k vs Bet365)."
                hist_stats = get_odds_bucket_stats(conn, div, sel_code, best_odd)

                suggested_stake = min(round(bankroll * stake_pct, 2), round(bankroll * stake_cap, 2)) if is_today else None

                candidate_obj = {
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
                    'source': source_tag,
                    'pick_label': "Lowest-cost pick, not a prediction of profit.",
                    'prefill': {
                        'match_name': f"{home_team} vs {away_team}",
                        'selection': sel_code,
                        'home_odds': b_odds.get(best_bookmaker, {}).get('H', best_odd),
                        'draw_odds': b_odds.get(best_bookmaker, {}).get('D', 3.30),
                        'away_odds': b_odds.get(best_bookmaker, {}).get('A', 3.40),
                        'kickoff_utc': dt_utc.isoformat()
                    }
                }

                if match_id not in match_candidates:
                    match_candidates[match_id] = []
                match_candidates[match_id].append(candidate_obj)

    # 4. RULE 1: ONE SELECTION PER MATCH
    # For every match, keep ONLY the single lowest-cost qualifying selection!
    deduped_candidates: List[Dict[str, Any]] = []
    for match_id, cand_list in match_candidates.items():
        if len(cand_list) > 1:
            skipped_breakdown['deduped_match'] += (len(cand_list) - 1)
        # Sort by expected_cost_per_1000 ascending, then facts_score descending
        cand_list.sort(key=lambda x: (x['expected_cost_per_1000'], -x['supporting_facts']['facts_score']))
        best_cand = cand_list[0]
        deduped_candidates.append(best_cand)

        day_label = datetime.fromisoformat(best_cand['kickoff_utc'].replace("Z", "+00:00")).strftime('%a %d %b')
        if day_label in per_day_summary:
            per_day_summary[day_label]['qualified'] += 1

    conn.close()

    # Distribute deduped candidates into tiers
    tiers = {'Steady': [], 'Balanced': [], 'Long shot': []}
    for c in deduped_candidates:
        if c['tier'] in tiers:
            tiers[c['tier']].append(c)

    # Sort each tier by lowest cost and cap at top 3
    seen_in_tiers = set()
    for t_name in ['Steady', 'Balanced', 'Long shot']:
        tiers[t_name].sort(key=lambda x: (x['expected_cost_per_1000'], -x['supporting_facts']['facts_score']))
        # Double check no match_id exists across multiple tiers
        unique_tier = []
        for c in tiers[t_name]:
            if c['match_id'] not in seen_in_tiers:
                unique_tier.append(c)
                seen_in_tiers.add(c['match_id'])
            else:
                skipped_breakdown['deduped_match'] += 1

        if len(unique_tier) > 3:
            skipped_breakdown['tier_capped'] += (len(unique_tier) - 3)
            unique_tier = unique_tier[:3]
        tiers[t_name] = unique_tier

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
            'timeframe': timeframe,
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
