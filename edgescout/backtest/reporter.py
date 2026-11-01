"""
Reporting & Visualization Module for EdgeScout.
Produces comprehensive backtest evaluation reports:
- Log Loss & Brier Score (benchmarked against Market & Uniform baselines)
- Reliability Calibration Plot & Table
- Flat-Stake ROI & P/L across Edge Thresholds
- Closing Line Value (CLV) Statistics
- Strictly enforces: DO NOT headline accuracy.
"""
from pathlib import Path
from typing import Dict, Any
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from edgescout.config import REPORTS_DIR, PLOTS_DIR


def generate_ascii_report(results: Dict[str, Any]) -> str:
    """
    Constructs a formatted text report with tables and probabilistic metrics.
    """
    lines = []
    lines.append("=" * 80)
    lines.append("                    EDGESCOUT QUANTITATIVE BACKTEST REPORT")
    lines.append("=" * 80)
    lines.append(f"Evaluation Window   : {results['start_date']} to {results['end_date']}")
    lines.append(f"Total Matches Eval  : {results['total_matches_evaluated']:,}")
    lines.append(f"Walk-Forward Folds  : {results['total_folds']}")
    lines.append("-" * 80)
    
    # 1. Probabilistic Scoring
    lines.append("1. PROBABILISTIC SCORING (Lower is superior; Accuracy deliberately omitted)")
    lines.append("-" * 80)
    lines.append(f"{'Metric':<25} | {'EdgeScout Model':<18} | {'Market De-Vigged':<18} | {'Uniform (1/3)':<15}")
    lines.append("-" * 80)
    lines.append(
        f"{'Multiclass Log Loss':<25} | {results['model_log_loss']:<18.4f} | "
        f"{results['market_log_loss']:<18.4f} | {results['uniform_log_loss']:<15.4f}"
    )
    lines.append(
        f"{'Multiclass Brier Score':<25} | {results['model_brier_score']:<18.4f} | "
        f"{results['market_brier_score']:<18.4f} | {results['uniform_brier_score']:<15.4f}"
    )
    lines.append(f"{'Expected Calib Error (ECE)':<25} | {results['expected_calibration_error']:<18.4f} | {'N/A':<18} | {'N/A':<15}")
    lines.append("")

    # 2. Calibration Reliability Table
    lines.append("2. PROBABILITY CALIBRATION ANALYSIS (Observed Frequency vs Predicted Mean)")
    lines.append("-" * 80)
    lines.append(f"{'Probability Bin':<18} | {'Sample Count':<14} | {'Pred Mean':<14} | {'Empirical Freq':<16} | {'Abs Error':<10}")
    lines.append("-" * 80)
    calib_df = results['calibration_table']
    for _, row in calib_df.iterrows():
        lines.append(
            f"{row['bin']:<18} | {int(row['count']):<14} | {row['predicted_mean']:<14.4f} | "
            f"{row['empirical_frequency']:<16.4f} | {row['error']:<10.4f}"
        )
    lines.append("")

    # 3. Flat-Stake Edge Threshold Performance
    lines.append("3. FLAT-STAKE PERFORMANCE ACROSS POSITIVE EV THRESHOLDS")
    lines.append("-" * 80)
    lines.append(f"{'Min Edge':<10} | {'Bets':<8} | {'Total Staked':<14} | {'P/L (Flat)':<12} | {'ROI (%)':<10} | {'Avg Edge':<10} | {'Avg CLV':<10} | {'Beat CL%':<10}")
    lines.append("-" * 80)
    eth_df = results['edge_thresholds_summary']
    for _, row in eth_df.iterrows():
        lines.append(
            f"{row['threshold_pct']:<10} | {int(row['num_bets']):<8} | "
            f"NGN {row['total_staked']:<10,.1f} | NGN {row['profit_loss']:<8,.1f} | "
            f"{row['roi_pct']:>6.2f}%    | {row['avg_edge_pct']:>6.2f}%   | "
            f"{row['avg_clv_pct']:>6.2f}%   | {row['beat_cl_pct']:>6.2f}%"
        )
    lines.append("=" * 80)
    lines.append("NOTE: Positive edge bets reflect structural market inefficiencies without outcome guarantees.")
    lines.append("=" * 80)

    return "\n".join(lines)


def generate_calibration_plot(calib_df: pd.DataFrame, output_path: Path = PLOTS_DIR / "calibration_plot.png"):
    """
    Plots the reliability diagram (calibration curve) comparing predicted vs actual frequency.
    """
    if calib_df.empty:
        return

    fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
    
    # Perfect calibration line
    ax.plot([0, 1], [0, 1], linestyle='--', color='#9A9AA3', label='Perfect Calibration')
    
    # Model points and line
    ax.plot(
        calib_df['predicted_mean'], 
        calib_df['empirical_frequency'], 
        marker='o', 
        color='#B49CFF', 
        linewidth=2, 
        markersize=7, 
        label='EdgeScout Model'
    )
    
    ax.set_title("Probability Calibration Reliability Curve", fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel("Predicted Probability Mean", fontsize=12)
    ax.set_ylabel("Empirical Outcome Frequency", fontsize=12)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, linestyle=':', alpha=0.6)
    ax.legend(frameon=True, facecolor='#232327', edgecolor='#4A4A52', labelcolor='#F4F2EA')
    
    # Styling
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
    Saves a GitHub-flavored markdown report with structured summary tables.
    """
    ascii_text = generate_ascii_report(results)
    
    md_content = f"""# EdgeScout Quantitative Backtest Report

**Evaluation Window:** {results['start_date']} to {results['end_date']}  
**Total Matches Evaluated:** {results['total_matches_evaluated']:,}  
**Walk-Forward Folds:** {results['total_folds']}

---

## 1. Probabilistic Evaluation (Strict Non-Accuracy Focus)

Unlike naive predictive models that headline win-loss prediction accuracy, EdgeScout evaluates probabilistic truth using strictly proper scoring rules.

| Metric | EdgeScout Model | Market De-Vigged (Shin) | Uniform Prior (1/3) | Interpretation |
| :--- | :--- | :--- | :--- | :--- |
| **Multiclass Log Loss** | `{results['model_log_loss']:.4f}` | `{results['market_log_loss']:.4f}` | `{results['uniform_log_loss']:.4f}` | Quantifies negative log probability of the true outcome (lower is superior). |
| **Brier Score** | `{results['model_brier_score']:.4f}` | `{results['market_brier_score']:.4f}` | `{results['uniform_brier_score']:.4f}` | Mean squared error of probability vector against one-hot outcome. |
| **Expected Calibration Error (ECE)** | `{results['expected_calibration_error']:.4f}` | N/A | N/A | Weighted absolute difference between confidence and empirical reality. |

---

## 2. Probability Calibration (Reliability Diagram)

A well-calibrated model ensures that among events assigned an x% probability, approximately x% occur in reality.

| Probability Bin | Matches In Bin | Predicted Mean | Empirical Win Frequency | Absolute Error |
| :--- | :--- | :--- | :--- | :--- |
"""
    for _, row in results['calibration_table'].iterrows():
        md_content += f"| `{row['bin']}` | {int(row['count']):,} | `{row['predicted_mean']:.4f}` | `{row['empirical_frequency']:.4f}` | `{row['error']:.4f}` |\n"

    md_content += f"""
![Calibration Curve](plots/calibration_plot.png)

---

## 3. Flat-Stake Performance Across Edge Thresholds

Simulating flat 100-unit stakes across matches where the model estimated expected value $\\ge$ threshold:

| Edge Threshold | Qualifying Bets | Total Staked | Net P/L | ROI (%) | Avg Model Edge | Avg CLV | Beat Closing Line % |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
"""
    for _, row in results['edge_thresholds_summary'].iterrows():
        md_content += (
            f"| **{row['threshold_pct']}** | {int(row['num_bets']):,} | "
            f"₦{row['total_staked']:,.2f} | ₦{row['profit_loss']:,.2f} | "
            f"**{row['roi_pct']:+.2f}%** | {row['avg_edge_pct']:.2f}% | "
            f"{row['avg_clv_pct']:+.2f}% | {row['beat_cl_pct']:.1f}% |\n"
        )

    md_content += """
---

## 4. Closing Line Value (CLV) Analysis
Closing Line Value is the gold standard benchmark in professional quantitative sports betting. Because closing lines represent the aggregate consensus of all sharp syndicates and liquidity right before kickoff, consistently beating the closing line is mathematical proof of finding pricing discrepancies.

---
*Generated automatically by EdgeScout Phase 1 Engine.*
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)

