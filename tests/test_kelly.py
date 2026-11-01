"""
Unit tests for Quarter-Kelly Criterion Staking Engine:
- Kelly fractional sizing
- Single-bet 2% bankroll cap
- Daily portfolio 6% total exposure cap
- Proportional scaling when daily exposure cap is breached
- Tier assignments
"""
import pytest
from edgescout.models.kelly import (
    kelly_fraction,
    calculate_stake,
    allocate_daily_portfolio
)


def test_quarter_kelly_calculation():
    # If p = 0.55 and odds = 2.0:
    # edge = 0.55 * 2.0 - 1 = 0.10
    # b = 2.0 - 1 = 1.0
    # full Kelly = 0.10 / 1.0 = 0.10 (10%)
    # Quarter Kelly = 10% / 4 = 2.5% = 0.025
    f_qk = kelly_fraction(0.55, 2.0, multiplier=0.25)
    assert pytest.approx(f_qk, abs=1e-5) == 0.025


def test_zero_stake_on_negative_or_zero_ev():
    # No edge (EV = 0)
    assert kelly_fraction(0.50, 2.0) == 0.0
    # Negative edge (EV < 0)
    assert kelly_fraction(0.40, 2.0) == 0.0
    # Invalid odds
    assert kelly_fraction(0.50, 0.95) == 0.0


def test_single_bet_cap():
    bankroll = 100_000.0
    # Massive edge: p = 0.80, odds = 3.0 -> full kelly = (2.4 - 1)/2 = 0.70 -> quarter = 0.175 (17.5%)
    raw_f, capped_f, stake = calculate_stake(
        p=0.80, 
        odds=3.0, 
        bankroll=bankroll, 
        kelly_mult=0.25, 
        max_bet_fraction=0.02
    )
    
    assert raw_f > 0.10
    assert capped_f == 0.02 # Capped at 2%
    assert stake == 2000.0  # 2% of 100,000


def test_daily_portfolio_cap_and_proportional_scaling():
    bankroll = 100_000.0
    # Create 5 bets, each qualifying for the 2% maximum single-bet cap
    # Total requested = 5 * 2% = 10%
    # But max daily exposure is 6%!
    bets = [
        {"match_id": f"m_{i}", "selection": "H", "model_prob": 0.65, "odds": 2.2, "market_prob": 0.45}
        for i in range(5)
    ]
    
    recs = allocate_daily_portfolio(
        bets=bets,
        bankroll=bankroll,
        kelly_mult=0.25,
        max_bet_fraction=0.02,
        max_daily_exposure=0.06
    )
    
    assert len(recs) == 5
    total_suggested_fraction = sum(r.suggested_fraction for r in recs)
    total_suggested_stake = sum(r.suggested_stake for r in recs)

    # Total exposure must not exceed 6%
    assert total_suggested_fraction <= 0.06001
    assert total_suggested_stake <= 6000.01

    # Each bet should be scaled down equally: 6% / 5 = 1.2% per bet
    for r in recs:
        assert pytest.approx(r.suggested_fraction, abs=1e-4) == 0.012
        assert pytest.approx(r.suggested_stake, abs=1.0) == 1200.0


def test_tier_classification():
    bankroll = 50_000.0
    bets = [
        # High confidence: p >= 0.55 and edge >= 0.05
        {"match_id": "hc", "selection": "H", "model_prob": 0.60, "odds": 1.90, "market_prob": 0.50},
        # Value: moderate prob, edge >= 0.03
        {"match_id": "val", "selection": "D", "model_prob": 0.35, "odds": 3.40, "market_prob": 0.28},
        # Longshot: odds >= 5.0
        {"match_id": "ls", "selection": "A", "model_prob": 0.22, "odds": 5.50, "market_prob": 0.17}
    ]
    recs = allocate_daily_portfolio(bets, bankroll)
    by_id = {r.match_id: r for r in recs}

    assert by_id["hc"].tier == "High Confidence"
    assert by_id["val"].tier == "Value"
    assert by_id["ls"].tier == "Long Shot"

