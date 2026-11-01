"""
Margin removal (de-vigging) module for EdgeScout.
Extracts fair market probabilities from bookmaker decimal odds using:
1. Proportional (Multiplicative / Normalization) method
2. Shin's method (accounting for insider trading and favourite-longshot bias)
"""
import numpy as np
from typing import Sequence, Tuple, Union
from scipy.optimize import root_scalar


def calculate_overround(odds: Sequence[float]) -> float:
    """
    Calculate the bookmaker overround (sum of implied probabilities - 1.0).
    E.g. If sum of 1/odds is 1.05, overround is 0.05 (5.0%).
    """
    arr = np.asarray(odds, dtype=float)
    if np.any(arr <= 1.0):
        raise ValueError(f"Odds must be greater than 1.0, got {odds}")
    return float(np.sum(1.0 / arr) - 1.0)


def remove_margin_proportional(odds: Sequence[float]) -> np.ndarray:
    """
    Proportional (multiplicative) margin removal:
    p_i = (1 / O_i) / sum(1 / O_j)
    
    Returns normalized probabilities summing to exactly 1.0.
    """
    arr = np.asarray(odds, dtype=float)
    if np.any(arr <= 1.0):
        raise ValueError(f"All odds must be > 1.0, got {odds}")
    inv = 1.0 / arr
    s = np.sum(inv)
    return inv / s


def remove_margin_shin(
    odds: Sequence[float], 
    tol: float = 1e-12, 
    max_iter: int = 100
) -> Tuple[np.ndarray, float]:
    """
    Shin's method for margin removal (Shin 1991, 1992, 1993; Clarke et al. 2017).
    Models the market as having an unknown fraction 'z' of informed/insider bettors
    and (1 - z) uninformed bettors.
    
    Formula for implied probability p_i given insider fraction z:
      p_i = (sqrt(z^2 + 4*(1 - z)*(beta_i^2 / S)) - z) / (2*(1 - z))
    where beta_i = 1 / O_i and S = sum(beta_i).
    
    We solve for z in [0, 1) such that sum(p_i) == 1.0.
    
    Returns:
      (probabilities, z)
    """
    arr = np.asarray(odds, dtype=float)
    if np.any(arr <= 1.0):
        raise ValueError(f"All odds must be > 1.0, got {odds}")
    
    beta = 1.0 / arr
    S = float(np.sum(beta))
    
    # If the market already has zero margin (S == 1.0)
    if np.isclose(S, 1.0, atol=1e-8):
        return beta / S, 0.0
    
    # If S < 1.0 (arbitrage / negative margin), normalize directly
    if S < 1.0:
        return beta / S, 0.0

    def objective(z: float) -> float:
        if np.isclose(z, 1.0, atol=1e-7):
            return -1.0
        term = np.sqrt(z**2 + 4.0 * (1.0 - z) * (beta**2) / S)
        p = (term - z) / (2.0 * (1.0 - z))
        return float(np.sum(p) - 1.0)

    try:
        # Shin's z is typically between 0.0 and 0.4
        sol = root_scalar(objective, bracket=[0.0, 0.9999], method='brentq', xtol=tol, maxiter=max_iter)
        z = sol.root
    except (ValueError, RuntimeError):
        # Fallback to bounded bisection if brentq fails
        lo, hi = 0.0, 0.9999
        z = 0.0
        for _ in range(max_iter):
            mid = (lo + hi) / 2.0
            val = objective(mid)
            if abs(val) < tol:
                z = mid
                break
            if val > 0:
                lo = mid
            else:
                hi = mid
            z = mid

    term = np.sqrt(z**2 + 4.0 * (1.0 - z) * (beta**2) / S)
    p = (term - z) / (2.0 * (1.0 - z))
    # Normalize tiny floating point deviations
    p = p / np.sum(p)
    return p, float(z)


def remove_margin(odds: Sequence[float], method: str = "shin") -> np.ndarray:
    """
    Convenience function to de-vig odds.
    method: 'shin' or 'proportional'
    """
    method = method.lower().strip()
    if method == "shin":
        probs, _ = remove_margin_shin(odds)
        return probs
    elif method in ("proportional", "prop", "multiplicative"):
        return remove_margin_proportional(odds)
    else:
        raise ValueError(f"Unknown margin removal method '{method}'. Choose 'shin' or 'proportional'.")


def calculate_ev(p_model: float, odds: float) -> float:
    """
    Expected Value of a bet:
    EV = (p_model * odds) - 1.0
    E.g. If p_model = 0.55 and odds = 2.00, EV = 0.10 (+10% edge).
    """
    if odds <= 1.0 or p_model < 0.0 or p_model > 1.0:
        return 0.0
    return float((p_model * odds) - 1.0)


def calculate_fair_odds(p: float) -> float:
    """Fair odds = 1 / p. Returns infinity if p <= 0."""
    if p <= 0.0:
        return float('inf')
    return float(1.0 / p)

