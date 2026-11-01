"""
Evaluation Metrics, Calibration, and Blending Engine for EdgeScout.
Implements:
- Multiclass Log Loss & Brier Score
- Bootstrap 95% Confidence Intervals
- Temperature / Platt Scaling Calibration
- Log-linear / Linear Blend of Model and Pinnacle Closing Probabilities
- Like-with-like CLV and Pinnacle Closing Value with Bootstrap CIs
- Edge Distribution Audit (by outcome and odds bucket)
- Suspected Model Error Audit (edges > 10%)
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Any, Optional
from scipy.optimize import minimize_scalar
from scipy.special import softmax


def multiclass_log_loss(
    y_true: List[str], 
    y_pred_probs: np.ndarray, 
    eps: float = 1e-15
) -> float:
    """Computes multiclass cross-entropy log loss."""
    mapping = {'H': 0, 'D': 1, 'A': 2}
    y_idx = np.array([mapping[res] for res in y_true])
    probs = np.clip(y_pred_probs, eps, 1.0 - eps)
    
    n_samples = len(y_true)
    if n_samples == 0:
        return 0.0
    
    actual_probs = probs[np.arange(n_samples), y_idx]
    return float(-np.mean(np.log(actual_probs)))


def multiclass_brier_score(
    y_true: List[str], 
    y_pred_probs: np.ndarray
) -> float:
    """Computes multiclass Brier score."""
    mapping = {'H': 0, 'D': 1, 'A': 2}
    n_samples = len(y_true)
    if n_samples == 0:
        return 0.0
        
    y_onehot = np.zeros((n_samples, 3))
    for i, res in enumerate(y_true):
        y_onehot[i, mapping[res]] = 1.0
        
    diff = y_pred_probs - y_onehot
    return float(np.mean(np.sum(diff ** 2, axis=1)))


def bootstrap_ci(
    data: np.ndarray, 
    stat_func=np.mean, 
    n_bootstraps: int = 1000, 
    ci: float = 0.95,
    random_state: int = 42
) -> Tuple[float, float, float]:
    """
    Computes (point_estimate, ci_lower, ci_upper) via percentile bootstrap.
    """
    arr = np.asarray(data)
    if len(arr) == 0:
        return 0.0, 0.0, 0.0
    point_est = float(stat_func(arr))
    if len(arr) < 5:
        return point_est, point_est, point_est

    rng = np.random.default_rng(random_state)
    boot_stats = np.empty(n_bootstraps)
    n = len(arr)
    for i in range(n_bootstraps):
        sample = rng.choice(arr, size=n, replace=True)
        boot_stats[i] = stat_func(sample)

    alpha = (1.0 - ci) / 2.0
    lo = float(np.percentile(boot_stats, 100.0 * alpha))
    hi = float(np.percentile(boot_stats, 100.0 * (1.0 - alpha)))
    return point_est, lo, hi


def bootstrap_log_loss_ci(
    y_true: List[str], 
    y_pred_probs: np.ndarray, 
    n_bootstraps: int = 1000,
    ci: float = 0.95
) -> Tuple[float, float, float]:
    """
    Computes bootstrap confidence interval for log loss.
    """
    mapping = {'H': 0, 'D': 1, 'A': 2}
    y_idx = np.array([mapping[res] for res in y_true])
    probs = np.clip(y_pred_probs, 1e-15, 1.0 - 1e-15)
    
    n_samples = len(y_true)
    actual_probs = probs[np.arange(n_samples), y_idx]
    individual_nll = -np.log(actual_probs)
    return bootstrap_ci(individual_nll, stat_func=np.mean, n_bootstraps=n_bootstraps, ci=ci)


def fit_temperature_scaling(
    y_true: List[str], 
    y_pred_probs: np.ndarray
) -> float:
    """
    Fits optimal temperature T on training fold probabilities to calibrate them.
    Minimizes multiclass cross-entropy loss.
    """
    mapping = {'H': 0, 'D': 1, 'A': 2}
    y_idx = np.array([mapping[res] for res in y_true])
    eps = 1e-12
    probs = np.clip(y_pred_probs, eps, 1.0)
    logits = np.log(probs)

    def obj(T: float) -> float:
        scaled_logits = logits / max(1e-4, T)
        cal_probs = softmax(scaled_logits, axis=1)
        actual_p = np.clip(cal_probs[np.arange(len(y_idx)), y_idx], 1e-15, 1.0)
        return float(-np.mean(np.log(actual_p)))

    res = minimize_scalar(obj, bounds=(0.5, 3.0), method='bounded')
    return float(res.x) if res.success else 1.0


def apply_temperature_scaling(
    y_pred_probs: np.ndarray, 
    temperature: float
) -> np.ndarray:
    """Applies temperature scaling to raw predicted probabilities."""
    eps = 1e-12
    probs = np.clip(y_pred_probs, eps, 1.0)
    logits = np.log(probs)
    scaled_logits = logits / max(1e-4, temperature)
    return softmax(scaled_logits, axis=1)


def fit_market_blend_weight(
    y_true: List[str],
    model_probs: np.ndarray,
    market_probs: np.ndarray
) -> float:
    """
    Finds optimal blend weight w in [0, 1] that minimizes log loss:
      p_blend = w * p_model + (1 - w) * p_market
    Trained strictly on training fold data.
    """
    mapping = {'H': 0, 'D': 1, 'A': 2}
    y_idx = np.array([mapping[res] for res in y_true])
    n = len(y_true)

    def obj(w: float) -> float:
        w_clamped = np.clip(w, 0.0, 1.0)
        p_blend = w_clamped * model_probs + (1.0 - w_clamped) * market_probs
        actual_p = np.clip(p_blend[np.arange(n), y_idx], 1e-15, 1.0)
        return float(-np.mean(np.log(actual_p)))

    res = minimize_scalar(obj, bounds=(0.0, 1.0), method='bounded')
    return float(res.x) if res.success else 0.0


def calculate_calibration_curve(
    predicted_probs: np.ndarray, 
    actual_outcomes: np.ndarray, 
    n_bins: int = 10
) -> pd.DataFrame:
    """
    Calculates calibration reliability curve across probability bins.
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
    """ECE = sum(weight_b * |pred_mean_b - actual_freq_b|)"""
    if calibration_df.empty:
        return 0.0
    return float(np.sum(calibration_df['weight'] * calibration_df['error']))


def audit_edge_distribution(bets_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Audits the edge distribution:
    1. Breakdown by outcome (Home, Draw, Away)
    2. Breakdown by odds bucket ([1.0, 1.5), [1.5, 2.0), [2.0, 3.0), [3.0, 5.0), [5.0, inf))
    3. Suspected model errors (edge > 10%)
    """
    if bets_df.empty:
        return {}

    # 1. By Outcome
    by_outcome = []
    for sel in ['H', 'D', 'A']:
        subset = bets_df[bets_df['selection'] == sel]
        n = len(subset)
        if n > 0:
            ret = float((subset['won'] * (100.0 * subset['odds_taken'])).sum())
            staked = float(n * 100.0)
            p_l = ret - staked
            roi = (p_l / staked) * 100.0
            by_outcome.append({
                'outcome': sel,
                'count': n,
                'pct_of_all_bets': (n / len(bets_df)) * 100.0,
                'mean_edge_pct': float(subset['edge'].mean()) * 100.0,
                'win_rate_pct': float(subset['won'].mean()) * 100.0,
                'roi_pct': roi
            })
    outcome_df = pd.DataFrame(by_outcome)

    # 2. By Odds Bucket
    odds_bins = [1.0, 1.5, 2.0, 3.0, 5.0, 100.0]
    bin_labels = ['1.0-1.5', '1.5-2.0', '2.0-3.0', '3.0-5.0', '5.0+']
    bets_df = bets_df.copy()
    bets_df['odds_bucket'] = pd.cut(bets_df['odds_taken'], bins=odds_bins, labels=bin_labels, right=False)

    by_bucket = []
    for label in bin_labels:
        subset = bets_df[bets_df['odds_bucket'] == label]
        n = len(subset)
        if n > 0:
            ret = float((subset['won'] * (100.0 * subset['odds_taken'])).sum())
            staked = float(n * 100.0)
            p_l = ret - staked
            roi = (p_l / staked) * 100.0
            by_bucket.append({
                'bucket': label,
                'count': n,
                'pct_of_all_bets': (n / len(bets_df)) * 100.0,
                'mean_edge_pct': float(subset['edge'].mean()) * 100.0,
                'win_rate_pct': float(subset['won'].mean()) * 100.0,
                'roi_pct': roi
            })
    bucket_df = pd.DataFrame(by_bucket)

    # 3. Suspected Model Errors (edge > 10%)
    high_edge_subset = bets_df[bets_df['edge'] > 0.10]
    n_high = len(high_edge_subset)
    high_edge_pct = (n_high / len(bets_df)) * 100.0 if len(bets_df) > 0 else 0.0

    ret_high = float((high_edge_subset['won'] * (100.0 * high_edge_subset['odds_taken'])).sum()) if n_high > 0 else 0.0
    staked_high = float(n_high * 100.0) if n_high > 0 else 0.0
    roi_high = ((ret_high - staked_high) / staked_high * 100.0) if staked_high > 0 else 0.0

    high_edge_summary = {
        'count': n_high,
        'pct_of_all_bets': high_edge_pct,
        'by_outcome': high_edge_subset['selection'].value_counts().to_dict() if n_high > 0 else {},
        'mean_edge': float(high_edge_subset['edge'].mean()) * 100.0 if n_high > 0 else 0.0,
        'win_rate_pct': float(high_edge_subset['won'].mean()) * 100.0 if n_high > 0 else 0.0,
        'roi_pct': roi_high
    }

    return {
        'by_outcome': outcome_df,
        'by_odds_bucket': bucket_df,
        'suspected_errors': high_edge_summary
    }


def evaluate_edge_thresholds_single_bet(
    bets_df: pd.DataFrame, 
    thresholds: List[float] = [0.02, 0.03, 0.05, 0.08, 0.10],
    flat_stake: float = 100.0
) -> pd.DataFrame:
    """
    Evaluates flat-stake betting across edge thresholds enforcing:
    AT MOST ONE BET PER MATCH (highest edge outcome).
    """
    summary = []
    
    for th in thresholds:
        qualifying = bets_df[bets_df['edge'] >= th].copy()
        
        if qualifying.empty:
            summary.append({
                'threshold': th,
                'threshold_pct': f"{th*100:.1f}%",
                'num_bets': 0,
                'total_staked': 0.0,
                'total_return': 0.0,
                'profit_loss': 0.0,
                'roi_pct': 0.0,
                'avg_edge_pct': 0.0,
                'avg_clv_b365_pct': 0.0,
                'avg_clv_pinnacle_pct': 0.0,
                'win_rate_pct': 0.0
            })
            continue

        # Strictly enforce AT MOST ONE BET PER MATCH (highest edge)
        qualifying = qualifying.sort_values('edge', ascending=False).drop_duplicates(subset=['match_id']).reset_index(drop=True)
        n_bets = len(qualifying)

        total_staked = n_bets * flat_stake
        returns = qualifying['won'] * (flat_stake * qualifying['odds_taken'])
        total_return = float(returns.sum())
        profit_loss = total_return - total_staked
        roi_pct = (profit_loss / total_staked) * 100.0
        
        avg_edge = float(qualifying['edge'].mean()) * 100.0
        
        # Like-with-like Bet365 CLV (where available)
        valid_b365_clv = qualifying['clv_b365'].dropna()
        avg_clv_b365 = float(valid_b365_clv.mean()) * 100.0 if len(valid_b365_clv) > 0 else 0.0

        # Pinnacle devigged closing probability CLV
        valid_pin_clv = qualifying['clv_pinnacle'].dropna()
        avg_clv_pin = float(valid_pin_clv.mean()) * 100.0 if len(valid_pin_clv) > 0 else 0.0

        win_rate = float(qualifying['won'].mean()) * 100.0

        summary.append({
            'threshold': th,
            'threshold_pct': f"{th*100:.1f}%",
            'num_bets': n_bets,
            'total_staked': round(total_staked, 2),
            'total_return': round(total_return, 2),
            'profit_loss': round(profit_loss, 2),
            'roi_pct': round(roi_pct, 2),
            'avg_edge_pct': round(avg_edge, 2),
            'avg_clv_b365_pct': round(avg_clv_b365, 2),
            'avg_clv_pinnacle_pct': round(avg_clv_pin, 2),
            'win_rate_pct': round(win_rate, 2)
        })

    return pd.DataFrame(summary)
