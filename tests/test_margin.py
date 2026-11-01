"""
Unit tests for margin removal (de-vigging) methods:
- Proportional (multiplicative)
- Shin's method (informed vs uninformed bettors)
"""
import pytest
import numpy as np
from edgescout.models.margin import (
    remove_margin_proportional,
    remove_margin_shin,
    remove_margin,
    calculate_overround,
    calculate_ev,
    calculate_fair_odds
)


def test_calculate_overround():
    # Odds of 2.0, 3.0, 4.0 -> sum(1/odds) = 0.5 + 0.3333 + 0.25 = 1.0833 (8.33% overround)
    odds = [2.0, 3.0, 4.0]
    ovr = calculate_overround(odds)
    assert pytest.approx(ovr, abs=1e-3) == 0.0833
    
    # Invalid odds <= 1.0 should raise ValueError
    with pytest.raises(ValueError):
        calculate_overround([0.9, 2.0, 3.0])


def test_remove_margin_proportional():
    odds = [2.60, 3.20, 2.90]
    probs = remove_margin_proportional(odds)
    
    assert len(probs) == 3
    assert np.all(probs > 0.0)
    assert np.all(probs < 1.0)
    assert pytest.approx(float(np.sum(probs)), abs=1e-7) == 1.0


def test_remove_margin_shin_sums_to_one():
    test_cases = [
        [2.60, 2.40, 4.30],
        [1.25, 6.00, 12.00],
        [3.10, 3.40, 2.30],
        [1.95, 3.60, 4.20],
        [1.05, 14.0, 35.0]
    ]
    for odds in test_cases:
        probs, z = remove_margin_shin(odds)
        assert len(probs) == len(odds)
        assert np.all(probs >= 0.0)
        assert pytest.approx(float(np.sum(probs)), abs=1e-6) == 1.0
        assert 0.0 <= z < 0.5, f"Insider fraction z={z} out of expected range for odds={odds}"


def test_shin_corrects_favorite_longshot_bias():
    """
    Shin's method should allocate a smaller fair probability to extreme longshots
    compared to the naive proportional method because bookmakers load heavier margin on longshots.
    """
    heavy_favorite_match = [1.20, 6.50, 15.00]
    prop_probs = remove_margin_proportional(heavy_favorite_match)
    shin_probs, z = remove_margin_shin(heavy_favorite_match)

    # For the extreme longshot (index 2, odds 15.0):
    # Shin probability should be LESS than naive proportional probability
    assert shin_probs[2] < prop_probs[2], (
        f"Shin ({shin_probs[2]:.5f}) should be lower than Proportional ({prop_probs[2]:.5f}) on longshot"
    )
    # And Shin probability on the favorite (index 0) should be HIGHER than proportional
    assert shin_probs[0] > prop_probs[0]


def test_remove_margin_convenience():
    odds = [2.0, 3.4, 3.8]
    shin = remove_margin(odds, method="shin")
    prop = remove_margin(odds, method="proportional")

    assert pytest.approx(float(np.sum(shin)), abs=1e-6) == 1.0
    assert pytest.approx(float(np.sum(prop)), abs=1e-6) == 1.0

    with pytest.raises(ValueError):
        remove_margin(odds, method="invalid_method")


def test_calculate_ev():
    # Model gives 60% probability at odds 2.0 -> EV = 0.60 * 2.0 - 1 = +0.20 (+20%)
    assert pytest.approx(calculate_ev(0.60, 2.0), abs=1e-5) == 0.20
    # Negative EV: 40% probability at odds 2.0 -> EV = 0.40 * 2.0 - 1 = -0.20 (-20%)
    assert pytest.approx(calculate_ev(0.40, 2.0), abs=1e-5) == -0.20
    # Neutral: 50% probability at odds 2.0 -> EV = 0.0
    assert pytest.approx(calculate_ev(0.50, 2.0), abs=1e-5) == 0.0


def test_calculate_fair_odds():
    assert pytest.approx(calculate_fair_odds(0.50), abs=1e-5) == 2.0
    assert pytest.approx(calculate_fair_odds(0.25), abs=1e-5) == 4.0
    assert calculate_fair_odds(0.0) == float('inf')

