"""
Execution script for Phase 1.6: Model-free soft vs sharp line audit.
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from edgescout.backtest.soft_vs_sharp import (
    load_soft_sharp_dataset, 
    calculate_overrounds_by_season, 
    run_soft_vs_sharp_audit
)

def main():
    df = load_soft_sharp_dataset()
    print(f"Loaded {len(df):,} clean matches with paired pre-close B365 and Pinnacle odds.\n")

    # 1. Overround Table
    ovr = calculate_overrounds_by_season(df)
    print("=" * 70)
    print("       TABLE 1: AVERAGE BOOKMAKER OVERROUND BY SEASON (%)")
    print("=" * 70)
    print(f"{'Season':<10} | {'Matches':<10} | {'Bet365 Overround':<18} | {'Pinnacle Overround':<18}")
    print("-" * 70)
    for _, r in ovr.iterrows():
        print(f"{r['season']:<10} | {int(r['matches']):<10} | {r['b365_overround_mean']:>14.2f}%   | {r['ps_overround_mean']:>14.2f}%")
    print("-" * 70)
    print(f"{'OVERALL':<10} | {int(ovr['matches'].sum()):<10} | {ovr['b365_overround_mean'].mean():>14.2f}%   | {ovr['ps_overround_mean'].mean():>14.2f}%")
    print("=" * 70)
    print()

    # 2. Soft vs Sharp Audit Across Thresholds
    res = run_soft_vs_sharp_audit(df)
    th_res = res['threshold_results']

    print("=" * 115)
    print("              TABLE 2: SOFT BOOK VS SHARP LINE PERFORMANCE BY MINIMUM EDGE THRESHOLD")
    print("=" * 115)
    print(f"{'Thresh':<8} | {'Total Bets':<11} | {'Bets/Sea':<9} | {'Hit Rate':<9} | {'Flat ROI':<10} | {'95% Bootstrap CI':<20} | {'Pin Close CLV':<14} | {'95% CI (Pin)':<18} | {'B365 CLV':<10} | {'Pos Seas':<9}")
    print("-" * 115)
    
    for t_str, d in th_res.items():
        roi_pt, roi_lo, roi_hi = d['roi_ci']
        pclv_pt, pclv_lo, pclv_hi = d['clv_pinnacle']
        bclv_pt, bclv_lo, bclv_hi = d['clv_b365']
        print(
            f"{t_str:<8} | {d['total_bets']:<11} | {d['bets_per_season']:<9.1f} | "
            f"{d['hit_rate']:>6.2f}%   | {d['roi']:>6.2f}%   | "
            f"[{roi_lo:>5.2f}%, {roi_hi:>5.2f}%]       | "
            f"{pclv_pt:>7.2f}%      | [{pclv_lo:>5.2f}%, {pclv_hi:>5.2f}%]   | "
            f"{bclv_pt:>6.2f}%    | {d['n_pos_seasons']}/{d['total_seasons']}"
        )
    print("=" * 115)
    print()

    # 3. Placebo Test Results
    print("=" * 80)
    print("                TABLE 3: PLACEBO TEST (1,000 RANDOM DRAWS)")
    print("=" * 80)
    print(f"{'Threshold':<12} | {'Real ROI':<10} | {'Placebo Mean':<14} | {'Placebo 95th Pct':<18} | {'Real ROI Percentile':<20}")
    print("-" * 80)
    for t_str, d in th_res.items():
        pl = d['placebo']
        print(
            f"{t_str:<12} | {d['roi']:>6.2f}%   | {pl['placebo_mean']:>10.2f}%   | "
            f"{pl['placebo_p95']:>12.2f}%     | {pl['real_roi_percentile']:>14.1f}%"
        )
    print("=" * 80)
    print()

    # 4. Breakdowns for Key Thresholds (0%, 1%, 2%, 3%, 5%)
    for t_str in ['0%', '1%', '2%', '3%', '5%']:
        if t_str not in th_res:
            continue
        d = th_res[t_str]
        print("=" * 80)
        print(f"        DETAILED BREAKDOWN FOR THRESHOLD >= {t_str}")
        print("=" * 80)
        print("A. Performance by Season:")
        print(f"   {'Season':<8} | {'Bets':<8} | {'Hit Rate':<10} | {'P/L (Flat)':<14} | {'ROI (%)':<10}")
        print("   " + "-" * 55)
        for _, s_row in d['by_season'].iterrows():
            print(f"   {s_row['season']:<8} | {int(s_row['bets']):<8} | {s_row['hit_rate_pct']:>6.2f}%    | ₦{s_row['pl']:<12,.1f} | {s_row['roi_pct']:>6.2f}%")
        print()
        print("B. Performance by League:")
        print(f"   {'League':<8} | {'Bets':<8} | {'P/L (Flat)':<14} | {'ROI (%)':<10}")
        print("   " + "-" * 45)
        for _, l_row in d['by_league'].iterrows():
            print(f"   {l_row['league']:<8} | {int(l_row['bets']):<8} | ₦{l_row['pl']:<12,.1f} | {l_row['roi_pct']:>6.2f}%")
        print()
        print("C. Performance by Odds Bucket:")
        print(f"   {'Bucket':<10} | {'Bets':<8} | {'P/L (Flat)':<14} | {'ROI (%)':<10}")
        print("   " + "-" * 45)
        for _, b_row in d['by_bucket'].iterrows():
            print(f"   {b_row['odds_bucket']:<10} | {int(b_row['bets']):<8} | ₦{b_row['pl']:<12,.1f} | {b_row['roi_pct']:>6.2f}%")
        print("=" * 80)
        print()

if __name__ == "__main__":
    main()

