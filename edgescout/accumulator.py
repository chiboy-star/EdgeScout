"""
Accumulator Cost & Compounded Margin Calculator for EdgeScout.
Quantifies the devastating effect of compounding bookmaker margins on multi-bets.
"""
from typing import List, Dict, Any
import numpy as np
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


class AccumulatorAnalysis(BaseModel):
    num_legs: int
    combined_odds: float
    combined_margin_pct: float
    true_combined_probability: float
    expected_loss_per_1000: float
    expected_return_per_1000: float
    single_bets_comparison: Dict[str, Any]
    legs_breakdown: List[Dict[str, Any]]


def calculate_accumulator(
    legs: List[Dict[str, Any]], 
    stake: float = 1000.0
) -> Dict[str, Any]:
    """
    Computes true compounding margin and expected loss for an accumulator.
    legs: List of dicts, each with 'odds' and optionally 'market_odds' [home, draw, away].
    """
    if not legs:
        return {
            'num_legs': 0,
            'combined_odds': 1.0,
            'combined_margin_pct': 0.0,
            'true_combined_probability': 1.0,
            'expected_loss_per_1000': 0.0,
            'expected_return_per_1000': 1000.0,
            'single_bets_comparison': {},
            'legs_breakdown': []
        }

    combined_odds = 1.0
    true_prob_product = 1.0
    margin_factors = 1.0
    legs_breakdown = []
    
    total_single_expected_loss = 0.0
    single_stake = stake / len(legs)

    for leg in legs:
        odds = float(leg['odds'])
        combined_odds *= odds
        
        # If full 1X2 market odds provided, de-vig using Shin; else assume default ~5.2% bookmaker margin
        market_odds = leg.get('market_odds', [])
        if len(market_odds) == 3 and all(o > 1.0 for o in market_odds):
            fair_probs, _ = remove_margin_shin(market_odds)
            sel_idx = leg.get('selection_index', 0)
            fair_p = float(fair_probs[sel_idx])
            margin = calculate_overround(market_odds)
        else:
            # Standard single-market margin proxy (5.2%)
            margin = 0.052
            fair_p = (1.0 / odds) / (1.0 + margin)

        true_prob_product *= fair_p
        # Margin compounding factor
        margin_factors *= (1.0 + margin)

        # Single bet expected loss
        single_loss = single_stake * (1.0 - (fair_p * odds))
        total_single_expected_loss += single_loss

        legs_breakdown.append({
            'selection': leg.get('selection', 'Selection'),
            'odds': odds,
            'fair_probability': round(fair_p, 4),
            'margin_pct': round(margin * 100.0, 2),
            'single_expected_loss': round(single_loss, 2)
        })

    # Combined overround across N independent events:
    # Prod(1 + m_i) - 1
    combined_margin_pct = (margin_factors - 1.0) * 100.0

    # Expected return of the accumulator:
    # EV = Stake * (True_Prob * Combined_Odds)
    expected_return = stake * (true_prob_product * combined_odds)
    expected_loss = stake - expected_return

    return {
        'num_legs': len(legs),
        'combined_odds': round(combined_odds, 2),
        'combined_margin_pct': round(combined_margin_pct, 2),
        'true_combined_probability': round(true_prob_product, 6),
        'expected_loss_per_1000': round(expected_loss * (1000.0 / stake), 2),
        'expected_return_per_1000': round(expected_return * (1000.0 / stake), 2),
        'single_bets_comparison': {
            'single_stake_each': round(single_stake, 2),
            'total_staked': round(stake, 2),
            'total_single_expected_loss': round(total_single_expected_loss, 2),
            'difference_vs_accumulator': round(expected_loss - total_single_expected_loss, 2)
        },
        'legs_breakdown': legs_breakdown
    }

