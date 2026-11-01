"""
Phase 1.6: Model-Free Test of "Soft Book vs Sharp Line".
Compares Bet365 pre-close odds against Pinnacle pre-close odds de-vigged with Shin.
Does NOT use any statistical goal model.
"""
import sqlite3
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any
from pathlib import Path

from edgescout.models.margin import remove_margin_shin
from edgescout.backtest.metrics import bootstrap_ci


def load_soft_sharp_dataset(db_path: str = "data/edgescout.sqlite3") -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    query = """
    SELECT 
        m.match_id, m.league_code, m.season, m.match_date, m.home_team, m.away_team, m.ftr,
        o.b365_h, o.b365_d, o.b365_a,
        o.ps_h, o.ps_d, o.ps_a,
        o.b365_ch, o.b365_cd, o.b365_ca,
        o.ps_ch, o.ps_cd, o.ps_ca
    FROM matches m
    JOIN odds o ON m.match_id = o.match_id
    WHERE m.ftr IN ('H', 'D', 'A')
      AND o.b365_h > 1.0 AND o.b365_d > 1.0 AND o.b365_a > 1.0
      AND o.ps_h > 1.0 AND o.ps_d > 1.0 AND o.ps_a > 1.0
      AND o.ps_ch > 1.0 AND o.ps_cd > 1.0 AND o.ps_ca > 1.0
    ORDER BY m.match_date ASC;
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df


def calculate_overrounds_by_season(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates average bookmaker overround by season for Bet365 and Pinnacle.
    """
    df = df.copy()
    df['b365_ovr'] = (1.0/df['b365_h'] + 1.0/df['b365_d'] + 1.0/df['b365_a'] - 1.0) * 100.0
    df['ps_ovr'] = (1.0/df['ps_h'] + 1.0/df['ps_d'] + 1.0/df['ps_a'] - 1.0) * 100.0
    
    grouped = df.groupby('season').agg(
        matches=('match_id', 'count'),
        b365_overround_mean=('b365_ovr', 'mean'),
        ps_overround_mean=('ps_ovr', 'mean')
    ).reset_index()
    return grouped


def run_soft_vs_sharp_audit(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Computes pre-close edge:
      pinnacle_fair_pre = Shin(PSH, PSD, PSA)
      edge = pinnacle_fair_pre * B365_pre - 1.0
    Evaluates at most one bet per match (highest edge) across thresholds {0%, 1%, 2%, 3%, 5%}.
    """
    records = []
    
    print(f"Processing {len(df):,} matches for soft vs sharp pre-close edge...")
    
    for idx, row in df.iterrows():
        b365_pre = [float(row['b365_h']), float(row['b365_d']), float(row['b365_a'])]
        ps_pre = [float(row['ps_h']), float(row['ps_d']), float(row['ps_a'])]
        ps_close = [float(row['ps_ch']), float(row['ps_cd']), float(row['ps_ca'])]
        
        # Bet365 closing odds where available
        b365_c_h = float(row['b365_ch']) if pd.notna(row.get('b365_ch')) and float(row.get('b365_ch')) > 1.0 else None
        b365_c_d = float(row['b365_cd']) if pd.notna(row.get('b365_cd')) and float(row.get('b365_cd')) > 1.0 else None
        b365_c_a = float(row['b365_ca']) if pd.notna(row.get('b365_ca')) and float(row.get('b365_ca')) > 1.0 else None
        b365_close_vec = [b365_c_h, b365_c_d, b365_c_a]

        # De-vig Pinnacle pre-close line with Shin
        p_pin_pre, _ = remove_margin_shin(ps_pre)

        # De-vig Pinnacle closing line with Shin (for post-match CLV evaluation only)
        p_pin_close, _ = remove_margin_shin(ps_close)

        ftr = row['ftr']
        selections = ['H', 'D', 'A']
        
        # Calculate edge for each selection
        match_edges = []
        for i, sel in enumerate(selections):
            o_b365 = b365_pre[i]
            p_fair = p_pin_pre[i]
            p_close_fair = p_pin_close[i]
            edge = (p_fair * o_b365) - 1.0
            
            # Like-with-like B365 CLV
            o_b365_c = b365_close_vec[i]
            clv_b365 = (o_b365 / o_b365_c - 1.0) if o_b365_c else None
            
            # Pinnacle de-vigged closing CLV
            clv_pin = (p_close_fair * o_b365) - 1.0
            
            won = 1 if ftr == sel else 0

            match_edges.append({
                'match_id': row['match_id'],
                'season': row['season'],
                'league': row['league_code'],
                'match_date': row['match_date'],
                'home_team': row['home_team'],
                'away_team': row['away_team'],
                'selection': sel,
                'b365_pre': o_b365,
                'ps_pre': ps_pre[i],
                'pin_fair_pre': p_fair,
                'pin_fair_close': p_close_fair,
                'edge': edge,
                'clv_b365': clv_b365,
                'clv_pinnacle': clv_pin,
                'ftr': ftr,
                'won': won
            })
            
        # Select highest-edge outcome for this match
        best_bet = max(match_edges, key=lambda x: x['edge'])
        records.append(best_bet)

    bets_df = pd.DataFrame(records)
    
    thresholds = [0.00, 0.01, 0.02, 0.03, 0.05]
    threshold_results = {}
    
    # Odds buckets
    odds_bins = [1.0, 1.5, 2.0, 3.0, 5.0, 100.0]
    bin_labels = ['1.0-1.5', '1.5-2.0', '2.0-3.0', '3.0-5.0', '5.0+']
    bets_df['odds_bucket'] = pd.cut(bets_df['b365_pre'], bins=odds_bins, labels=bin_labels, right=False)

    total_seasons = bets_df['season'].nunique()

    for t in thresholds:
        t_pct = f"{t*100:.0f}%"
        sub = bets_df[bets_df['edge'] >= t].copy()
        n_bets = len(sub)
        
        if n_bets == 0:
            threshold_results[t_pct] = {'n_bets': 0}
            continue

        staked = n_bets * 100.0
        ret = float((sub['won'] * (100.0 * sub['b365_pre'])).sum())
        pl = ret - staked
        roi = (pl / staked) * 100.0
        hit_rate = float(sub['won'].mean()) * 100.0

        # Bootstrap CI for ROI
        individual_returns = sub['won'] * sub['b365_pre'] - 1.0 # fractional ROI per bet
        roi_pt, roi_lo, roi_hi = bootstrap_ci(individual_returns.values * 100.0)

        # CLV stats
        valid_b365_clv = sub['clv_b365'].dropna().values
        b365_clv_mean, b365_clv_lo, b365_clv_hi = bootstrap_ci(valid_b365_clv * 100.0) if len(valid_b365_clv) > 0 else (0.0, 0.0, 0.0)

        valid_pin_clv = sub['clv_pinnacle'].dropna().values
        pin_clv_mean, pin_clv_lo, pin_clv_hi = bootstrap_ci(valid_pin_clv * 100.0)

        # By Season
        by_season = sub.groupby('season').agg(
            bets=('match_id', 'count'),
            won=('won', 'sum'),
            staked=('won', lambda x: len(x) * 100.0),
            returns=('won', lambda x: float((x * sub.loc[x.index, 'b365_pre'] * 100.0).sum()))
        ).reset_index()
        by_season['pl'] = by_season['returns'] - by_season['staked']
        by_season['roi_pct'] = (by_season['pl'] / by_season['staked']) * 100.0
        by_season['hit_rate_pct'] = (by_season['won'] / by_season['bets']) * 100.0
        n_pos_seasons = int((by_season['roi_pct'] > 0).sum())

        # By League
        by_league = sub.groupby('league').agg(
            bets=('match_id', 'count'),
            won=('won', 'sum'),
            staked=('won', lambda x: len(x) * 100.0),
            returns=('won', lambda x: float((x * sub.loc[x.index, 'b365_pre'] * 100.0).sum()))
        ).reset_index()
        by_league['pl'] = by_league['returns'] - by_league['staked']
        by_league['roi_pct'] = (by_league['pl'] / by_league['staked']) * 100.0

        # By Odds Bucket
        by_bucket = sub.groupby('odds_bucket', observed=False).agg(
            bets=('match_id', 'count'),
            won=('won', 'sum'),
            staked=('won', lambda x: len(x) * 100.0),
            returns=('won', lambda x: float((x * sub.loc[x.index, 'b365_pre'] * 100.0).sum()))
        ).reset_index()
        by_bucket['pl'] = by_bucket['returns'] - by_bucket['staked']
        by_bucket['roi_pct'] = (by_bucket['pl'] / by_bucket['staked']) * 100.0

        # Placebo Test: 1,000 random selections
        rng = np.random.default_rng(42)
        placebo_rois = np.empty(1000)
        
        # In the placebo test, we randomly pick an outcome for each match where a bet was placed
        # or randomly draw from the pool of matches
        all_possible_returns = []
        for _, row in df.loc[sub.index].iterrows():
            sel_rnd = rng.choice(['H', 'D', 'A'])
            odds_rnd = float(row[f'b365_{sel_rnd.lower()}'])
            w = 1.0 if row['ftr'] == sel_rnd else 0.0
            all_possible_returns.append(w * odds_rnd - 1.0)
            
        all_possible_returns = np.array(all_possible_returns)
        for i in range(1000):
            sample = rng.choice(all_possible_returns, size=n_bets, replace=True)
            placebo_rois[i] = np.mean(sample) * 100.0
            
        placebo_p_val = float(np.mean(placebo_rois >= roi))
        placebo_percentile = float(np.mean(placebo_rois <= roi)) * 100.0
        placebo_mean = float(np.mean(placebo_rois))
        placebo_p95 = float(np.percentile(placebo_rois, 95.0))

        threshold_results[t_pct] = {
            'threshold_pct': t_pct,
            'total_bets': n_bets,
            'bets_per_season': round(n_bets / total_seasons, 1),
            'hit_rate': hit_rate,
            'roi': roi,
            'roi_ci': (roi_pt, roi_lo, roi_hi),
            'clv_pinnacle': (pin_clv_mean, pin_clv_lo, pin_clv_hi),
            'clv_b365': (b365_clv_mean, b365_clv_lo, b365_clv_hi),
            'n_pos_seasons': n_pos_seasons,
            'total_seasons': total_seasons,
            'by_season': by_season,
            'by_league': by_league,
            'by_bucket': by_bucket,
            'placebo': {
                'placebo_mean': placebo_mean,
                'placebo_p95': placebo_p95,
                'real_roi_percentile': placebo_percentile,
                'p_value': placebo_p_val
            }
        }

    return {
        'total_matches': len(df),
        'threshold_results': threshold_results,
        'bets_df': bets_df
    }

