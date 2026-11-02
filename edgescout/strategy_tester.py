"""
Strategy Tester Engine for EdgeScout.
Backtests user-defined betting rules on 13 stored historical seasons (23,459 real matches).
Strictly separates:
- Design / In-Sample: Seasons 2012/13 through 2019/20 (8 seasons)
- Holdout / Out-of-Sample: Seasons 2020/21 through 2024/25 (5 seasons)

Persists trial counter in SQLite to track multiple-hypothesis testing (data-mining penalty).
Headlines holdout results and compares against the bookmaker margin baseline.
"""
import sqlite3
import json
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from edgescout.config import DEFAULT_DB_PATH
from edgescout.backtest.metrics import bootstrap_ci

DESIGN_SEASONS = ['1213', '1314', '1415', '1516', '1617', '1718', '1819', '1920']
HOLDOUT_SEASONS = ['2021', '2122', '2223', '2324', '2425']


class StrategyRule:
    def __init__(
        self,
        name: str = "Custom Rule",
        leagues: Optional[List[str]] = None,
        min_odds: float = 1.01,
        max_odds: float = 100.0,
        selections: Optional[List[str]] = None, # ['H', 'D', 'A']
        role_filter: str = "ALL",               # "FAVOURITE", "UNDERDOG", "ALL"
        odds_source: str = "b365"
    ):
        self.name = name
        self.leagues = leagues or ["E0", "SP1", "I1", "D1", "F1"]
        self.min_odds = min_odds
        self.max_odds = max_odds
        self.selections = selections or ["H", "D", "A"]
        self.role_filter = role_filter.upper()
        self.odds_source = odds_source


def init_strategy_trials_table(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS strategy_trials (
        trial_id INTEGER PRIMARY KEY AUTOINCREMENT,
        executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        rule_description TEXT NOT NULL,
        leagues TEXT NOT NULL,
        selections TEXT NOT NULL,
        role_filter TEXT NOT NULL,
        min_odds REAL NOT NULL,
        max_odds REAL NOT NULL,
        odds_source TEXT NOT NULL,
        design_bets INTEGER NOT NULL,
        design_roi REAL NOT NULL,
        design_ci_low REAL NOT NULL,
        design_ci_high REAL NOT NULL,
        holdout_bets INTEGER NOT NULL,
        holdout_roi REAL NOT NULL,
        holdout_ci_low REAL NOT NULL,
        holdout_ci_high REAL NOT NULL,
        holdout_baseline REAL NOT NULL,
        verdict TEXT NOT NULL
    );
    """)
    conn.commit()


def _evaluate_subset(df_subset: pd.DataFrame, flat_stake: float) -> Dict[str, Any]:
    n_bets = len(df_subset)
    if n_bets == 0:
        return {
            'total_bets': 0,
            'total_staked': 0.0,
            'total_returned': 0.0,
            'net_profit_loss': 0.0,
            'realized_roi_pct': 0.0,
            'roi_95_ci': (0.0, 0.0, 0.0),
            'hit_rate_pct': 0.0,
            'margin_baseline_loss_pct': 0.0,
            'difference_vs_margin_pct': 0.0
        }

    total_staked = n_bets * flat_stake
    total_returned = float(df_subset['returns'].sum())
    net_pl = total_returned - total_staked
    roi_pct = (net_pl / total_staked) * 100.0
    hit_rate_pct = float(df_subset['won'].mean()) * 100.0

    # Margin baseline: expected loss given bookmaker overround
    expected_margin_loss_pct = float(df_subset['margin_baseline_loss_pct'].mean())

    # Bootstrap 95% Confidence Interval for ROI
    fractional_returns = (df_subset['returns'] - flat_stake) / flat_stake
    roi_pt, roi_lo, roi_hi = bootstrap_ci(fractional_returns.values * 100.0)

    return {
        'total_bets': n_bets,
        'total_staked': round(total_staked, 2),
        'total_returned': round(total_returned, 2),
        'net_profit_loss': round(net_pl, 2),
        'realized_roi_pct': round(roi_pct, 2),
        'roi_95_ci': (round(roi_pt, 2), round(roi_lo, 2), round(roi_hi, 2)),
        'hit_rate_pct': round(hit_rate_pct, 2),
        'margin_baseline_loss_pct': round(expected_margin_loss_pct, 2),
        'difference_vs_margin_pct': round(roi_pct - expected_margin_loss_pct, 2)
    }


def run_strategy_test(
    rule: StrategyRule, 
    db_path: str = str(DEFAULT_DB_PATH),
    flat_stake: float = 100.0,
    log_trial: bool = True
) -> Dict[str, Any]:
    """
    Executes a user rule across 13 historical seasons in SQLite,
    strictly separating 2012/13-2019/20 (Design) from 2020/21-2024/25 (Holdout).
    Headlines the Holdout result.
    Persists trial to `strategy_trials` table.
    """
    conn = sqlite3.connect(db_path)
    init_strategy_trials_table(conn)

    query = """
    SELECT 
        m.match_id, m.league_code, m.season, m.match_date, m.home_team, m.away_team, m.ftr,
        o.b365_h, o.b365_d, o.b365_a,
        o.ps_h, o.ps_d, o.ps_a,
        o.ps_ch, o.ps_cd, o.ps_ca
    FROM matches m
    JOIN odds o ON m.match_id = o.match_id
    WHERE m.ftr IN ('H', 'D', 'A')
      AND o.b365_h > 1.0 AND o.b365_d > 1.0 AND o.b365_a > 1.0
    ORDER BY m.match_date ASC;
    """
    df = pd.read_sql_query(query, conn)

    qualifying_bets = []

    for _, row in df.iterrows():
        league = row['league_code']
        if league not in rule.leagues:
            continue

        b365_odds = {
            'H': float(row['b365_h']),
            'D': float(row['b365_d']),
            'A': float(row['b365_a'])
        }
        
        # Determine favourite and underdog in this match
        min_match_odd = min(b365_odds.values())
        max_match_odd = max(b365_odds.values())

        # Bookmaker overround for margin baseline: - (overround / (1 + overround)) * 100
        overround = (1.0/b365_odds['H'] + 1.0/b365_odds['D'] + 1.0/b365_odds['A'] - 1.0)
        margin_baseline_loss_pct = -(overround / (1.0 + overround)) * 100.0

        for sel in rule.selections:
            odd = b365_odds[sel]
            
            # Check odds range
            if not (rule.min_odds <= odd <= rule.max_odds):
                continue

            # Check role filter
            if rule.role_filter == "FAVOURITE" and odd > min_match_odd:
                continue
            elif rule.role_filter == "UNDERDOG" and odd < max_match_odd:
                continue

            won = 1 if row['ftr'] == sel else 0
            returns = won * (flat_stake * odd)
            pl = returns - flat_stake

            qualifying_bets.append({
                'match_id': row['match_id'],
                'season': str(row['season']),
                'league': league,
                'match_date': row['match_date'],
                'home_team': row['home_team'],
                'away_team': row['away_team'],
                'selection': sel,
                'odds': odd,
                'margin_baseline_loss_pct': margin_baseline_loss_pct,
                'won': won,
                'staked': flat_stake,
                'returns': returns,
                'pl': pl
            })

    if not qualifying_bets:
        conn.close()
        return {
            'total_bets': 0,
            'message': 'No bets matched the specified criteria.'
        }

    bets_df = pd.DataFrame(qualifying_bets)

    # Split into Design (2012/13 - 2019/20) and Holdout (2020/21 - 2024/25)
    design_df = bets_df[bets_df['season'].isin(DESIGN_SEASONS)]
    holdout_df = bets_df[bets_df['season'].isin(HOLDOUT_SEASONS)]

    design_stats = _evaluate_subset(design_df, flat_stake)
    holdout_stats = _evaluate_subset(holdout_df, flat_stake)
    overall_stats = _evaluate_subset(bets_df, flat_stake)

    # Seasonal Breakdown
    seasonal_summary = []
    for s_name, s_group in bets_df.groupby('season'):
        s_n = len(s_group)
        s_stk = s_n * flat_stake
        s_ret = float(s_group['returns'].sum())
        s_pl = s_ret - s_stk
        s_roi = (s_pl / s_stk) * 100.0 if s_stk > 0 else 0.0
        seasonal_summary.append({
            'season': s_name,
            'split': 'HOLDOUT' if s_name in HOLDOUT_SEASONS else 'DESIGN',
            'bets': s_n,
            'win_rate_pct': round(float(s_group['won'].mean()) * 100.0, 2),
            'profit_loss': round(s_pl, 2),
            'roi_pct': round(s_roi, 2)
        })

    # Plain language statistical verdict based strictly on HOLDOUT:
    # Verdict stays "indistinguishable from the margin" unless holdout ROI CI is entirely above the margin baseline
    h_ci_lo = holdout_stats['roi_95_ci'][1]
    h_ci_hi = holdout_stats['roi_95_ci'][2]
    h_baseline = holdout_stats['margin_baseline_loss_pct']

    if holdout_stats['total_bets'] == 0:
        verdict = "INSUFFICIENT HOLDOUT DATA (Zero qualifying bets in 2020/21-2024/25)."
    elif h_ci_lo > h_baseline:
        if h_ci_lo > 0:
            verdict = (
                f"STATISTICAL ANOMALY ON HOLDOUT: 95% CI [{h_ci_lo}%, {h_ci_hi}%] is strictly positive. "
                "Verify for data-mining bias or execution slippage."
            )
        else:
            verdict = (
                f"HOLDOUT EXCEEDS MARGIN BASELINE: 95% CI [{h_ci_lo}%, {h_ci_hi}%] is entirely above "
                f"the expected overround loss ({h_baseline}%)."
            )
    elif h_ci_hi < h_baseline:
        verdict = (
            f"STATISTICALLY WORSE THAN MARGIN ON HOLDOUT: 95% CI [{h_ci_lo}%, {h_ci_hi}%] is below "
            f"the overround baseline ({h_baseline}%). Suffers from excess vig or negative longshot bias."
        )
    else:
        verdict = (
            f"INDISTINGUISHABLE FROM THE MARGIN. Holdout outcome (ROI {holdout_stats['realized_roi_pct']}%, "
            f"95% CI [{h_ci_lo}%, {h_ci_hi}%]) is fully explained by normal variance around bookmaker vig ({h_baseline}%)."
        )

    # Persist trial in database
    if log_trial:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO strategy_trials (
            rule_description, leagues, selections, role_filter, min_odds, max_odds, odds_source,
            design_bets, design_roi, design_ci_low, design_ci_high,
            holdout_bets, holdout_roi, holdout_ci_low, holdout_ci_high, holdout_baseline,
            verdict
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            rule.name,
            ",".join(rule.leagues),
            ",".join(rule.selections),
            rule.role_filter,
            rule.min_odds,
            rule.max_odds,
            rule.odds_source,
            design_stats['total_bets'],
            design_stats['realized_roi_pct'],
            design_stats['roi_95_ci'][1],
            design_stats['roi_95_ci'][2],
            holdout_stats['total_bets'],
            holdout_stats['realized_roi_pct'],
            h_ci_lo,
            h_ci_hi,
            h_baseline,
            verdict
        ))
        conn.commit()

    # Query total trials counter
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM strategy_trials;")
    total_trials = int(cur.fetchone()[0])
    conn.close()

    expected_false_positives = round(0.05 * total_trials, 2)
    multiple_testing_warning = (
        f"⚠️ Multiple-Testing Notice: You have executed {total_trials} strategy test(s). "
        f"Under standard α = 0.05 significance, expect ~{expected_false_positives} rules to appear statistically "
        "significant purely by random chance (data-snooping bias)."
    )

    odds_proxy_note = (
        "Odds reference: Bet365 pre-close odds. Real-world SportyBet margins are typically 1.0%–2.5% higher "
        "(5.5%–7.5% vs Bet365's 4.5%–5.5%), so realized net returns on soft retail books will be correspondingly worse."
    )

    return {
        # Headlined Holdout metrics
        'headlined_split': 'HOLDOUT (2020/21 – 2024/25)',
        'holdout': holdout_stats,
        'design': design_stats,
        'overall': overall_stats,
        'verdict': verdict,
        'total_trials_run': total_trials,
        'multiple_testing_warning': multiple_testing_warning,
        'expected_false_positives': expected_false_positives,
        'odds_proxy_note': odds_proxy_note,
        'seasonal_breakdown': seasonal_summary,
        # Top-level backwards compatibility fields
        'total_bets': overall_stats['total_bets'],
        'realized_roi_pct': holdout_stats['realized_roi_pct'],
        'roi_95_ci': holdout_stats['roi_95_ci'],
        'hit_rate_pct': holdout_stats['hit_rate_pct'],
        'margin_baseline_expected_loss_pct': holdout_stats['margin_baseline_loss_pct'],
        'difference_vs_margin_pct': holdout_stats['difference_vs_margin_pct']
    }
