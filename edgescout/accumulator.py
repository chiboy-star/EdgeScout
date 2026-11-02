"""
Accumulator Cost & Compounded Margin Calculator for EdgeScout.
Quantifies the mathematically devastating effect of compounding bookmaker margins on multi-bets.

Audited Mathematical Model:
For N independent events each carrying bookmaker margin m_i:
1. Compounded Margin Overround:
   M = Product_{i=1}^N (1 + m_i) - 1
2. Expected Loss per Stake:
   Expected Loss Fraction = 1 - 1 / (1 + M)
   Expected Return Fraction = 1 / (1 + M)

Example:
4 legs at 5.3% each (m_i = 0.053):
1 + M = (1.053)^4 = 1.22956
M = 22.96%
Expected Loss = 1 - (1 / 1.22956) = 18.67% (~18.7%)
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from edgescout.models.margin import remove_margin_shin, calculate_overround


class AccumulatorLeg(BaseModel):
    match_id: str
    match_name: str
    selection: str
    odds: float
    market_odds_1x2: List[float] = Field(default_factory=list)
    individual_margin: float = 0.0
    fair_probability: float = 0.0


def calculate_accumulator(
    legs: List[Dict[str, Any]], 
    stake: float = 1000.0
) -> Dict[str, Any]:
    """
    Computes true compounding margin and expected loss for an accumulator.
    Expected Loss Fraction = 1 - 1 / (1 + M) where M = Product(1 + m_i) - 1.
    """
    if not legs:
        return {
            'num_legs': 0,
            'combined_odds': 1.0,
            'compounded_margin_m': 0.0,
            'compounded_margin_pct': 0.0,
            'expected_loss_fraction': 0.0,
            'expected_loss_pct': 0.0,
            'true_combined_probability': 1.0,
            'expected_loss': 0.0,
            'expected_return': stake,
            'expected_loss_per_1000': 0.0,
            'expected_return_per_1000': 1000.0,
            'has_correlated_legs': False,
            'correlation_warning': None,
            'formula_tooltip': "Expected loss fraction = 1 - 1/(1+M), where M = ∏(1+m_i) - 1",
            'single_bets_comparison': {},
            'legs_breakdown': []
        }

    combined_odds = 1.0
    true_prob_product = 1.0
    margin_factors = 1.0
    legs_breakdown = []
    match_identifiers = []
    
    total_single_expected_loss = 0.0
    single_stake = stake / len(legs)

    for leg in legs:
        odds = float(leg['odds'])
        combined_odds *= odds
        m_id = str(leg.get('match_id') or leg.get('match_name') or leg.get('match', ''))
        if m_id:
            match_identifiers.append(m_id)
        
        # If full 1X2 market odds provided, compute exact margin; else use individual_margin or default 5.3%
        market_odds = leg.get('market_odds', []) or leg.get('market_odds_1x2', [])
        if len(market_odds) == 3 and all(o > 1.0 for o in market_odds):
            fair_probs, _ = remove_margin_shin(market_odds)
            sel_idx = leg.get('selection_index', 0)
            fair_p = float(fair_probs[sel_idx])
            margin = calculate_overround(market_odds)
        elif 'individual_margin' in leg and leg['individual_margin'] > 0:
            margin = float(leg['individual_margin'])
            fair_p = (1.0 / odds) / (1.0 + margin)
        else:
            # Standard single-market margin proxy (5.3% per audit baseline)
            margin = 0.053
            fair_p = (1.0 / odds) / (1.0 + margin)

        true_prob_product *= fair_p
        margin_factors *= (1.0 + margin)

        # Single bet expected loss: 1 - 1/(1 + margin)
        single_loss_fraction = 1.0 - (1.0 / (1.0 + margin))
        single_loss = single_stake * single_loss_fraction
        total_single_expected_loss += single_loss

        legs_breakdown.append({
            'match_id': m_id,
            'selection': leg.get('selection', 'Selection'),
            'odds': round(odds, 2),
            'fair_probability': round(fair_p, 4),
            'margin_pct': round(margin * 100.0, 2),
            'single_expected_loss': round(single_loss, 2),
            'single_loss_pct': round(single_loss_fraction * 100.0, 2)
        })

    # Compounding Overround: M = Product(1 + m_i) - 1
    compounded_margin_m = margin_factors - 1.0
    compounded_margin_pct = compounded_margin_m * 100.0

    # Audited Expected Loss:
    # Expected Loss Fraction = 1 - 1 / (1 + M)
    expected_loss_fraction = 1.0 - (1.0 / margin_factors)
    expected_loss_pct = expected_loss_fraction * 100.0

    expected_loss = stake * expected_loss_fraction
    expected_return = stake * (1.0 - expected_loss_fraction)

    # Correlated legs check
    has_correlated_legs = len(match_identifiers) > len(set(match_identifiers))
    correlation_warning = None
    if has_correlated_legs:
        correlation_warning = (
            "⚠️ Correlated legs detected: Multiple selections belong to the same fixture. "
            "Match outcomes are not independent; the standard accumulator compounding formula does not apply."
        )

    return {
        'num_legs': len(legs),
        'combined_odds': round(combined_odds, 2),
        'compounded_margin_m': round(compounded_margin_m, 4),
        'compounded_margin_pct': round(compounded_margin_pct, 2),
        'combined_margin_pct': round(compounded_margin_pct, 2), # backwards compatibility alias
        'expected_loss_fraction': round(expected_loss_fraction, 4),
        'expected_loss_pct': round(expected_loss_pct, 2),
        'true_combined_probability': round(true_prob_product, 6),
        'expected_loss': round(expected_loss, 2),
        'expected_return': round(expected_return, 2),
        'expected_loss_per_1000': round(1000.0 * expected_loss_fraction, 2),
        'expected_return_per_1000': round(1000.0 * (1.0 - expected_loss_fraction), 2),
        'has_correlated_legs': has_correlated_legs,
        'correlation_warning': correlation_warning,
        'formula_tooltip': "Expected loss per stake = 1 - 1/(1+M) where M = ∏(1+m_i) - 1",
        'single_bets_comparison': {
            'single_stake_each': round(single_stake, 2),
            'total_staked': round(stake, 2),
            'total_single_expected_loss': round(total_single_expected_loss, 2),
            'difference_vs_accumulator': round(expected_loss - total_single_expected_loss, 2)
        },
        'legs_breakdown': legs_breakdown
    }
