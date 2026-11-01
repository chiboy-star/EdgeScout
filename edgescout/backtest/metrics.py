"""
Evaluation Metrics & Calibration Engine for EdgeScout.
Implements:
- Multiclass Log Loss (Cross-Entropy)
- Multiclass Brier Score
- Expected Calibration Error (ECE) & Reliability Bins
- ROI & Flat-Stake P/L at Edge Thresholds
- Closing Line Value (CLV) Statistics
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any, Optional


def multiclass_log_loss(
    y_true: List[str], 
    y_pred_probs: np.ndarray, 
    eps: float = 1e-15
) -> float:
    """
    Computes multiclass cross-entropy log loss.
    y_true: List of 'H', 'D', 'A'
    y_pred_probs: (N, 3) matrix corresponding to columns [H, D, A]
    """
    mapping = {'H': 0, 'D': 1, 'A': 2}
    y_idx = np.array([mapping[res] for res in y_true])
    probs = np.clip(y_pred_probs, eps, 1.0 - eps)
    
    n_samples = len(y_true)
    if n_samples == 0:
        return 0.0
    
    # Extract predicted probability for the actual outcome
    actual_probs = probs[np.arange(n_samples), y_idx]
    return float(-np.mean(np.log(actual_probs)))


def multiclass_brier_score(
    y_true: List[str], 
    y_pred_probs: np.ndarray
) -> float:
    """
    Computes multiclass Brier score:
    Brier = (1 / N) * sum_i sum_k (p_{i,k} - y_{i,k})^2
    Lower is better (0.0 = perfect probabilistic forecast).
    """
    mapping = {'H': 0, 'D': 1, 'A': 2}
    n_samples = len(y_true)
    if n_samples == 0:
        return 0.0
        
    y_onehot = np.zeros((n_samples, 3))
    for i, res in enumerate(y_true):
        y_onehot[i, mapping[res]] = 1.0
        
    diff = y_pred_probs - y_onehot
    return float(np.mean(np.sum(diff ** 2, axis=1)))


def calculate_calibration_curve(
    predicted_probs: np.ndarray, 
    actual_outcomes: np.ndarray, 
    n_bins: int = 10
) -> pd.DataFrame:
    """
    Calculates calibration reliability curve across probability bins.
    predicted_probs: 1D array of predicted probabilities
    actual_outcomes: 1D binary array (1 for event occurred, 0 otherwise)
    """
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(predicted_probs, bins) - 1
    
    records = []
    total_samples = len(predicted_probs)
    
    for i in range(n_bins):
        mask = (bin_indices == i)
        count = int(np.sum(mask))
        if count > 0:
            mean_pred = float(np.mean(predicted_probs[mask]))
            empirical_freq = float(np.mean(actual_outcomes[mask]))
            records.append({
                'bin': f"{bins[i]:.1f}-{bins[i+1]:.1f}",
                'bin_center': (bins[i] + bins[i+1]) / 2.0,
                'count': count,
                'weight': count / total_samples,
                'predicted_mean': mean_pred,
                'empirical_frequency': empirical_freq,
                'error': abs(mean_pred - empirical_freq)
            })
            
    df = pd.DataFrame(records)
    return df


def calculate_expected_calibration_error(calibration_df: pd.DataFrame) -> float:
    """
    ECE = sum(weight_b * |pred_mean_b - actual_freq_b|)
    """
    if calibration_df.empty:
        return 0.0
    return float(np.sum(calibration_df['weight'] * calibration_df['error']))


def calculate_clv(odds_taken: float, closing_odds: float) -> float:
    """
    Closing Line Value (CLV):
    CLV = (Odds_taken / Odds_closing) - 1.0
    Positive CLV indicates beating the sharp closing market.
    """
    if closing_odds <= 1.0 or odds_taken <= 1.0:
        return 0.0
    return float((odds_taken / closing_odds) - 1.0)


def evaluate_edge_thresholds(
    bets_df: pd.DataFrame, 
    thresholds: List[float] = [0.02, 0.03, 0.05, 0.08, 0.10],
    flat_stake: float = 100.0
) -> pd.DataFrame:
    """
    Simulates flat-stake betting across various minimum edge thresholds.
    bets_df must contain: 'edge', 'odds_taken', 'closing_odds', 'won'
    """
    summary = []
    for th in thresholds:
        qualifying = bets_df[bets_df['edge'] >= th].copy()
        n_bets = len(qualifying)
        
        if n_bets == 0:
            summary.append({
                'threshold': th,
                'threshold_pct': f"{th*100:.1f}%",
                'num_bets': 0,
                'total_staked': 0.0,
                'total_return': 0.0,
                'profit_loss': 0.0,
                'roi_pct': 0.0,
                'avg_edge_pct': 0.0,
                'avg_clv_pct': 0.0,
                'win_rate_pct': 0.0,
                'beat_cl_pct': 0.0
            })
            continue

        total_staked = n_bets * flat_stake
        # Won bet pays: flat_stake * odds_taken; lost bet returns 0
        returns = qualifying['won'] * (flat_stake * qualifying['odds_taken'])
        total_return = float(returns.sum())
        profit_loss = total_return - total_staked
        roi_pct = (profit_loss / total_staked) * 100.0
        
        avg_edge = float(qualifying['edge'].mean()) * 100.0
        avg_clv = float(qualifying['clv'].mean()) * 100.0 if 'clv' in qualifying.columns else 0.0
        win_rate = float(qualifying['won'].mean()) * 100.0
        beat_cl = float((qualifying['clv'] > 0).mean()) * 100.0 if 'clv' in qualifying.columns else 0.0

        summary.append({
            'threshold': th,
            'threshold_pct': f"{th*100:.1f}%",
            'num_bets': n_bets,
            'total_staked': round(total_staked, 2),
            'total_return': round(total_return, 2),
            'profit_loss': round(profit_loss, 2),
            'roi_pct': round(roi_pct, 2),
            'avg_edge_pct': round(avg_edge, 2),
            'avg_clv_pct': round(avg_clv, 2),
            'win_rate_pct': round(win_rate, 2),
            'beat_cl_pct': round(beat_cl, 2)
        })

    return pd.DataFrame(summary)

