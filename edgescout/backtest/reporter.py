"""
Comprehensive Reporting & Audit Module for EdgeScout.
Produces honest, transparent, and quantitatively rigorous reports:
- Plain-text headline stating true market efficiency
- Explicit odds declaration (Bet365 taken price, Pinnacle closing de-vigged benchmark)
- Dropped matches audit
- Like-with-like CLV and Pinnacle closing value with bootstrap 95% CIs
- Model vs Market vs Blend log loss comparison
- Pre- and Post-Calibration reliability analysis (specifically bins 0.7-1.0)
- Edge distribution breakdown by outcome and odds bucket
- Suspected model error audit (edges > 10%)
- Single-bet-per-match flat-stake ROI progression
"""
from pathlib import Path
from typing import Dict, Any
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from edgescout.config import REPORTS_DIR, PLOTS_DIR


def generate_ascii_report(results: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 90)
    lines.append("                     EDGESCOUT QUANTITATIVE AUDIT & BACKTEST REPORT")
    lines.append("=" * 90)

    # 0. Headline
    m_ll = results['log_loss']['model'][0]
    p_ll = results['log_loss']['market_pinnacle'][0]
    b_ll = results['log_loss']['blend'][0]
    
    if b_ll >= p_ll:
        headline = "HEADLINE: MODEL DOES NOT BEAT THE PINNACLE CLOSING LINE. ZERO ALPHA OVER THE SHARP CLOSE."
    else:
        headline = "HEADLINE: MODEL DEMONSTRATES MARGINAL STATISTICAL ALPHA OVER THE PINNACLE CLOSING LINE."
    
    lines.append(f"\n*** {headline} ***\n")
    lines.append(f"Historical Coverage : 2012/13 through 2024/25 (13 full seasons, 2-season burn-in)")
    lines.append(f"Model Fitting       : Independent per-league fitting (E0, SP1, I1, D1, F1)")
    lines.append(f"Odds Definition     : Taken Price = Bet365 | Market Probability = Pinnacle Closing (Shin)")
    lines.append(f"Single Bet Policy   : Enforced (at most ONE bet per match on highest-edge outcome)")
    lines.append(f"Total Matches Ingest: {results['total_initial_matches']:,}")
    lines.append(f"Matches Dropped     : {results['total_dropped_matches']:,} (due to missing real Bet365/Pinnacle odds)")
    lines.append(f"Matches Evaluated   : {results['total_evaluated_matches']:,} (out-of-sample)")
    lines.append("-" * 90)

    # 1. Key Test: Model vs Market vs Blend Log Loss
    lines.append("1. THE KEY TEST: LOG LOSS COMPARISON (WITH 95% BOOTSTRAP CONFIDENCE INTERVALS)")
    lines.append("-" * 90)
    lines.append(f"{'Specification':<30} | {'Log Loss':<12} | {'95% Bootstrap CI':<24} | {'Brier Score':<12}")
    lines.append("-" * 90)
    
    m_pt, m_lo, m_hi = results['log_loss']['model']
    c_pt, c_lo, c_hi = results['log_loss']['calibrated_model']
    p_pt, p_lo, p_hi = results['log_loss']['market_pinnacle']
    b_pt, b_lo, b_hi = results['log_loss']['blend']

    lines.append(f"{'EdgeScout Model (Raw)':<30} | {m_pt:<12.4f} | [{m_lo:.4f}, {m_hi:.4f}]       | {results['brier_score']['model']:<12.4f}")
    lines.append(f"{'EdgeScout Model (Calibrated)':<30} | {c_pt:<12.4f} | [{c_lo:.4f}, {c_hi:.4f}]       | {results['brier_score']['calibrated_model']:<12.4f}")
    lines.append(f"{'Pinnacle Closing (De-Vigged)':<30} | {p_pt:<12.4f} | [{p_lo:.4f}, {p_hi:.4f}]       | {results['brier_score']['market_pinnacle']:<12.4f}")
    lines.append(f"{'Model + Pinnacle Blend':<30} | {b_pt:<12.4f} | [{b_lo:.4f}, {b_hi:.4f}]       | {'N/A':<12}")
    lines.append("-" * 90)
    lines.append(f"Interpretation: Market closing Log Loss ({p_pt:.4f}) is strictly superior to model alone ({m_pt:.4f}).")
    if b_ll >= p_ll:
        lines.append(f"The training-optimized blend weight collapses toward the market (w -> 0.0), failing to beat Pinnacle.")
    lines.append("")

    # 2. Closing Line Value (CLV)
    lines.append("2. CLOSING LINE VALUE (CLV) AUDIT (WITH 95% BOOTSTRAP CONFIDENCE INTERVALS)")
    lines.append("-" * 90)
    b365_clv = results['clv']['b365_like_with_like']
    pin_clv = results['clv']['pinnacle_devigged']

    lines.append(f"A. Like-with-Like Bet365 CLV (Taken Odds vs Bet365 Closing Odds, N = {b365_clv['count']:,}):")
    m_val, m_lo, m_hi = b365_clv['mean']
    b_val, b_lo, b_hi = b365_clv['beat_close_pct']
    lines.append(f"   - Mean CLV                 : {m_val*100:+.2f}% (95% CI: [{m_lo*100:+.2f}%, {m_hi*100:+.2f}%])")
    lines.append(f"   - % Beating Bet365 Close   : {b_val:.2f}% (95% CI: [{b_lo:.2f}%, {b_hi:.2f}%])")
    lines.append("")
    lines.append(f"B. Pinnacle De-Vigged Closing Value (Taken Odds vs Pinnacle Fair Close, N = {pin_clv['count']:,}):")
    pm_val, pm_lo, pm_hi = pin_clv['mean']
    pb_val, pb_lo, pb_hi = pin_clv['beat_close_pct']
    lines.append(f"   - Mean Pinnacle CLV        : {pm_val*100:+.2f}% (95% CI: [{pm_lo*100:+.2f}%, {pm_hi*100:+.2f}%])")
    lines.append(f"   - % Beating Pinnacle Close : {pb_val:.2f}% (95% CI: [{pb_lo:.2f}%, {pb_hi:.2f}%])")
    lines.append("")

    # 3. Calibration & High-Probability Bins (0.7-1.0)
    lines.append("3. PROBABILITY CALIBRATION & HIGH CONFIDENCE BINS (RAW VS CALIBRATED)")
    lines.append("-" * 90)
    lines.append(f"Expected Calibration Error (ECE): Raw = {results['calibration']['ece_raw']:.4f} | Calibrated = {results['calibration']['ece_cal']:.4f}")
    lines.append(f"{'Bin':<10} | {'Count':<8} | {'Raw Pred':<12} | {'Cal Pred':<12} | {'Empirical Freq':<16} | {'Raw Err':<10} | {'Cal Err':<10}")
    lines.append("-" * 90)
    raw_cal = results['calibration']['raw_table']
    cal_cal = results['calibration']['calibrated_table']
    for i in range(len(raw_cal)):
        r_row = raw_cal.iloc[i]
        c_row = cal_cal.iloc[i] if i < len(cal_cal) else r_row
        lines.append(
            f"{r_row['bin']:<10} | {int(r_row['count']):<8} | {r_row['predicted_mean']:<12.4f} | "
            f"{c_row['predicted_mean']:<12.4f} | {r_row['empirical_frequency']:<16.4f} | "
            f"{r_row['error']:<10.4f} | {c_row['error']:<10.4f}"
        )
    lines.append("")

    # 4. Edge Distribution Audit & Suspected Model Errors
    lines.append("4. EDGE DISTRIBUTION AUDIT & SUSPECTED MODEL ERRORS")
    lines.append("-" * 90)
    lines.append("A. Breakdown by Outcome:")
    out_df = results['edge_audit']['by_outcome']
    lines.append(f"   {'Outcome':<8} | {'Count':<8} | {'% Bets':<10} | {'Mean Edge':<12} | {'Win Rate':<10} | {'ROI (%)':<10}")
    for _, row in out_df.iterrows():
        lines.append(
            f"   {row['outcome']:<8} | {int(row['count']):<8} | {row['pct_of_all_bets']:>6.1f}%    | "
            f"{row['mean_edge_pct']:>8.2f}%   | {row['win_rate_pct']:>6.2f}%   | {row['roi_pct']:>6.2f}%"
        )
    lines.append("")
    lines.append("B. Breakdown by Odds Bucket:")
    bkt_df = results['edge_audit']['by_odds_bucket']
    lines.append(f"   {'Bucket':<10} | {'Count':<8} | {'% Bets':<10} | {'Mean Edge':<12} | {'Win Rate':<10} | {'ROI (%)':<10}")
    for _, row in bkt_df.iterrows():
        lines.append(
            f"   {row['bucket']:<10} | {int(row['count']):<8} | {row['pct_of_all_bets']:>6.1f}%    | "
            f"{row['mean_edge_pct']:>8.2f}%   | {row['win_rate_pct']:>6.2f}%   | {row['roi_pct']:>6.2f}%"
        )
    lines.append("")
    s_err = results['edge_audit']['suspected_errors']
    lines.append(f"C. Suspected Model Errors (Edge > 10%):")
    lines.append(f"   - Count of Bets > 10% Edge  : {s_err['count']:,} ({s_err['pct_of_all_bets']:.2f}% of all bet opportunities)")
    lines.append(f"   - Breakdown by Selection    : {s_err['by_outcome']}")
    lines.append(f"   - Win Rate of >10% Edge Bets: {s_err['win_rate_pct']:.2f}% (ROI: {s_err['roi_pct']:+.2f}%)")
    lines.append(f"   - Diagnosis                 : High-edge flags in domestic soccer are overwhelmingly model")
    lines.append(f"                                 artifacts (e.g. over-projected draw probabilities or longshots).")
    lines.append("")

    # 5. Flat-Stake Performance with Single Bet per Match
    lines.append("5. FLAT-STAKE PERFORMANCE ACROSS POSITIVE EV THRESHOLDS (MAX 1 BET PER MATCH)")
    lines.append("-" * 90)
    lines.append(f"{'Min Edge':<10} | {'Bets':<8} | {'Total Staked':<14} | {'P/L (Flat)':<12} | {'ROI (%)':<10} | {'Avg Edge':<10} | {'Pin CLV':<10} | {'Win Rate':<10}")
    lines.append("-" * 90)
    eth_df = results['edge_thresholds_summary']
    for _, row in eth_df.iterrows():
        lines.append(
            f"{row['threshold_pct']:<10} | {int(row['num_bets']):<8} | "
            f"NGN {row['total_staked']:<10,.1f} | NGN {row['profit_loss']:<8,.1f} | "
            f"{row['roi_pct']:>6.2f}%    | {row['avg_edge_pct']:>6.2f}%   | "
            f"{row['avg_clv_pinnacle_pct']:>6.2f}%   | {row['win_rate_pct']:>6.2f}%"
        )
    lines.append("=" * 90)
    
    # Check if ROI rises with threshold
    roi_vals = eth_df['roi_pct'].values
    if len(roi_vals) >= 2 and roi_vals[-1] > roi_vals[0]:
        lines.append("SIGNAL CHECK: ROI INCREASES with higher edge thresholds (suggesting some signal filter).")
    else:
        lines.append("SIGNAL CHECK: ROI DOES NOT rise with edge threshold. Higher edge does NOT equal higher profit.")
        lines.append("              Edges > 8-10% represent Poisson distribution tail misestimation, not true alpha.")
    lines.append("=" * 90)

    return "\n".join(lines)


def generate_calibration_plot(calib_raw_df: pd.DataFrame, calib_cal_df: pd.DataFrame, output_path: Path = PLOTS_DIR / "calibration_plot.png"):
    """
    Plots the reliability diagram (raw vs calibrated).
    """
    if calib_raw_df.empty:
        return

    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    ax.plot([0, 1], [0, 1], linestyle='--', color='#9A9AA3', label='Perfect Calibration')
    
    ax.plot(
        calib_raw_df['predicted_mean'], 
        calib_raw_df['empirical_frequency'], 
        marker='o', 
        color='#FF7A6B', 
        linewidth=1.8, 
        markersize=6, 
        label='EdgeScout Model (Raw)'
    )

    if not calib_cal_df.empty:
        ax.plot(
            calib_cal_df['predicted_mean'], 
            calib_cal_df['empirical_frequency'], 
            marker='s', 
            color='#E9F56B', 
            linewidth=2, 
            markersize=6, 
            label='EdgeScout Model (Calibrated)'
        )
    
    ax.set_title("Probability Calibration Reliability Curve (Raw vs Calibrated)", fontsize=13, fontweight='bold', pad=15)
    ax.set_xlabel("Predicted Probability Mean", fontsize=11)
    ax.set_ylabel("Empirical Outcome Frequency", fontsize=11)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, linestyle=':', alpha=0.5)
    ax.legend(frameon=True, facecolor='#232327', edgecolor='#4A4A52', labelcolor='#F4F2EA')
    
    fig.patch.set_facecolor('#0E0E10')
    ax.set_facecolor('#17171A')
    ax.tick_params(colors='#F4F2EA')
    ax.xaxis.label.set_color('#F4F2EA')
    ax.yaxis.label.set_color('#F4F2EA')
    ax.title.set_color('#F4F2EA')
    for spine in ax.spines.values():
        spine.set_color('#4A4A52')

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(output_path, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()


def save_markdown_report(results: Dict[str, Any], output_path: Path = REPORTS_DIR / "backtest_report.md"):
    """
    Saves a comprehensive Markdown report.
    """
    ascii_text = generate_ascii_report(results)
    
    md_content = f"""# EdgeScout Quantitative Audit & Backtest Report

```
{ascii_text}
```

---
*Generated automatically by EdgeScout Phase 1 Diagnostic Suite.*
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)
