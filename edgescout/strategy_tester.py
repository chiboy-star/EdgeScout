"""
Strategy Tester Engine for EdgeScout.
Backtests user-defined betting rules on 13 stored historical seasons (23,459 real matches).
Compares realized results against the bookmaker margin baseline.
Default verdict: 'Indistinguishable from bookmaker margin'.
"""
import sqlite3
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Any
from pathlib import Path

from edgescout.config import DEFAULT_DB_PATH
from edgescout.backtest.metrics import bootstrap_ci


class StrategyRule:
    def __init__(
        self,
        leagues: Optional[List[str]] = None,
        min_odds: float = 1.01,
        max_odds: float = 100.0,
        selections: Optional[List[str]] = None, # ['H', 'D', 'A']
        role_filter: str = "ALL",               # "FAVOURITE", "UNDERDOG", "ALL"
        odds_source: str = "b365"
    ):
        self.leagues = leagues or ["E0", "SP1", "I1", "D1", "F1"]
        self.min_odds = min_odds
        self.max_odds = max_odds
        self.selections = selections or ["H", "D", "A"]
        self.role_filter = role_filter.upper()
        self.odds_source = odds_source


def run_strategy_test(
    rule: StrategyRule, 
    db_path: str = str(DEFAULT_DB_PATH),
    flat_stake: float = 100.0
) -> Dict[str, Any]:
    """
    Executes a user rule across 13 historical seasons in SQLite.
    """
    conn = sqlite3.connect(db_path)
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
    conn.close()

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

        # Bookmaker overround for margin baseline
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
                'season': row['season'],
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
        return {
            'total_bets': 0,
            'message': 'No bets matched the specified criteria.'
        }

    bets_df = pd.DataFrame(qualifying_bets)
    n_bets = len(bets_df)
    total_staked = n_bets * flat_stake
    total_returned = float(bets_df['returns'].sum())
    net_pl = total_returned - total_staked
    roi_pct = (net_pl / total_staked) * 100.0
    hit_rate_pct = float(bets_df['won'].mean()) * 100.0

    # Margin baseline: expected loss given bookmaker overround
    expected_margin_loss_pct = float(bets_df['margin_baseline_loss_pct'].mean())

    # Bootstrap 95% Confidence Interval for ROI
    fractional_returns = (bets_df['returns'] - flat_stake) / flat_stake
    roi_pt, roi_lo, roi_hi = bootstrap_ci(fractional_returns.values * 100.0)

    # Seasonal Breakdown
    seasonal_summary = []
    for s_name, s_group in bets_df.groupby('season'):
        s_n = len(s_group)
        s_stk = s_n * flat_stake
        s_ret = float(s_group['returns'].sum())
        s_pl = s_ret - s_stk
        s_roi = (s_pl / s_stk) * 100.0
        seasonal_summary.append({
            'season': s_name,
            'bets': s_n,
            'win_rate_pct': round(float(s_group['won'].mean()) * 100.0, 2),
            'profit_loss': round(s_pl, 2),
            'roi_pct': round(s_roi, 2)
        })

    # Plain language statistical verdict
    # Default is: Indistinguishable from bookmaker margin
    if roi_lo > 0:
        verdict = "Statistical Anomaly (Statistically significant positive return; verify for survivor bias or regulatory limits)."
    elif roi_hi < expected_margin_loss_pct:
        verdict = "Statistically Worse Than Random: Suffers from excess bookmaker margin or negative longshot bias."
    else:
        verdict = "INDISTINGUISHABLE FROM THE MARGIN. Outcome is fully explained by normal variance and bookmaker vig."

    return {
        'total_bets': n_bets,
        'bets_per_season': round(n_bets / bets_df['season'].nunique(), 1),
        'total_staked': round(total_staked, 2),
        'total_returned': round(total_returned, 2),
        'net_profit_loss': round(net_pl, 2),
        'realized_roi_pct': round(roi_pct, 2),
        'roi_95_ci': (round(roi_pt, 2), round(roi_lo, 2), round(roi_hi, 2)),
        'hit_rate_pct': round(hit_rate_pct, 2),
        'margin_baseline_expected_loss_pct': round(expected_margin_loss_pct, 2),
        'difference_vs_margin_pct': round(roi_pct - expected_margin_loss_pct, 2),
        'verdict': verdict,
        'seasonal_breakdown': seasonal_summary
    }

