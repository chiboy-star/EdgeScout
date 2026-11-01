"""
Unit tests for Strategy Tester Engine:
Tests backtesting user rules across 13 stored seasons.
"""
import pytest
from edgescout.strategy_tester import StrategyRule, run_strategy_test
from edgescout.config import DEFAULT_DB_PATH


def test_strategy_tester_home_favourites():
    rule = StrategyRule(
        leagues=["E0"],
        min_odds=1.20,
        max_odds=1.80,
        selections=["H"],
        role_filter="FAVOURITE"
    )
    res = run_strategy_test(rule, db_path=str(DEFAULT_DB_PATH))

    assert res['total_bets'] > 500
    assert 'realized_roi_pct' in res
    assert 'roi_95_ci' in res
    assert 'margin_baseline_expected_loss_pct' in res
    assert 'verdict' in res
    assert len(res['seasonal_breakdown']) > 5
    # Expected margin loss must be negative (bookmaker takes vig)
    assert res['margin_baseline_expected_loss_pct'] < 0.0


def test_strategy_tester_empty_filter():
    rule = StrategyRule(
        leagues=["E0"],
        min_odds=50.0,
        max_odds=100.0,
        selections=["D"]
    )
    res = run_strategy_test(rule, db_path=str(DEFAULT_DB_PATH))
    assert res['total_bets'] == 0

