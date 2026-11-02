"""
Unit tests for audited Accumulator Cost & Compounded Margin Calculator.
Verifies:
1. Expected loss fraction = 1 - 1 / (1 + M) where M = Product(1 + m_i) - 1.
2. 4 legs at 5.3% each (m_i = 0.053) gives ~18.7% (18.67%) expected loss.
3. Detects correlated legs when multiple selections share the same fixture.
"""
import pytest
from edgescout.accumulator import calculate_accumulator


def test_accumulator_audited_formula_4_legs_at_5_point_3_percent():
    """
    User requirement:
    '4 legs at 5.3% each should give about 18.7%.'
    M = (1.053)^4 - 1 = 0.229562... (22.96% overround)
    Expected loss = 1 - 1/(1+M) = 1 - 1/1.229562 = 0.18670... = 18.67% ~ 18.7%
    """
    legs = [
        {'match_id': f'match_{i}', 'odds': 2.0, 'individual_margin': 0.053}
        for i in range(4)
    ]
    res = calculate_accumulator(legs, stake=1000.0)

    # Compounded overround M
    assert pytest.approx(res['compounded_margin_pct'], rel=1e-2) == 22.96

    # Expected loss percentage must be ~18.7% (18.67%), NOT 22.96%!
    assert pytest.approx(res['expected_loss_pct'], rel=1e-2) == 18.67
    assert pytest.approx(res['expected_loss_per_1000'], rel=1e-2) == 186.70

    # Expected return per 1000 must be 1000 - 186.70 = 813.30
    assert pytest.approx(res['expected_return_per_1000'], rel=1e-2) == 813.30


def test_accumulator_correlated_legs_warning():
    """
    Verifies that multiple legs from the same fixture trigger a prominent warning.
    """
    # Two legs from the same match 'ARS_CHE'
    legs = [
        {'match_id': 'ARS_CHE', 'match_name': 'Arsenal vs Chelsea', 'selection': 'Arsenal', 'odds': 1.85},
        {'match_id': 'ARS_CHE', 'match_name': 'Arsenal vs Chelsea', 'selection': 'Draw', 'odds': 3.75},
        {'match_id': 'MCI_LIV', 'match_name': 'Man City vs Liverpool', 'selection': 'Man City', 'odds': 2.05}
    ]
    res = calculate_accumulator(legs, stake=1000.0)

    assert res['has_correlated_legs'] is True
    assert "Correlated legs detected" in res['correlation_warning']


def test_accumulator_independent_legs_no_warning():
    """
    Verifies that distinct fixtures do not trigger correlation warning.
    """
    legs = [
        {'match_id': 'ARS_CHE', 'match_name': 'Arsenal vs Chelsea', 'selection': 'Arsenal', 'odds': 1.85},
        {'match_id': 'MCI_LIV', 'match_name': 'Man City vs Liverpool', 'selection': 'Man City', 'odds': 2.05}
    ]
    res = calculate_accumulator(legs, stake=1000.0)

    assert res['has_correlated_legs'] is False
    assert res['correlation_warning'] is None

