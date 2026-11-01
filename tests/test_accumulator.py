"""
Unit tests for Accumulator Math & Compounding Margin Calculator.
"""
import pytest
from edgescout.accumulator import calculate_accumulator


def test_single_leg_accumulator():
    # Single leg: odds 2.0 with market odds [2.0, 3.4, 4.0]
    legs = [{'odds': 2.0, 'market_odds': [2.0, 3.4, 4.0], 'selection_index': 0}]
    res = calculate_accumulator(legs, stake=1000.0)
    
    assert res['num_legs'] == 1
    assert res['combined_odds'] == 2.0
    assert res['combined_margin_pct'] > 0.0
    # Expected return + expected loss must equal stake
    assert pytest.approx(res['expected_loss_per_1000'] + res['expected_return_per_1000'], abs=1e-1) == 1000.0


def test_accumulator_margin_compounds():
    # 3 legs, each with ~5.2% margin
    # Compounded margin = (1.052)^3 - 1 = 1.164 - 1 = ~16.4%
    legs = [
        {'odds': 1.80},
        {'odds': 2.10},
        {'odds': 1.95}
    ]
    res = calculate_accumulator(legs, stake=1000.0)
    
    assert res['num_legs'] == 3
    assert res['combined_odds'] == round(1.80 * 2.10 * 1.95, 2)
    # Compounded margin must be strictly greater than a single leg's margin
    assert res['combined_margin_pct'] > 15.0
    # Expected loss on 1000 must be significant (> 120)
    assert res['expected_loss_per_1000'] > 120.0
    # Comparison shows accumulator expected loss is higher than single bets
    diff = res['single_bets_comparison']['difference_vs_accumulator']
    assert diff > 0.0 # Accumulator is mathematically more costly than single bets


def test_empty_accumulator():
    res = calculate_accumulator([], stake=1000.0)
    assert res['num_legs'] == 0
    assert res['expected_loss_per_1000'] == 0.0

