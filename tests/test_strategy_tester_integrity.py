"""
Unit tests for Strategy Tester Integrity, Design vs Holdout Splits, and Trial Counter Persistence.
"""
import pytest
import sqlite3
import tempfile
from pathlib import Path

from edgescout.strategy_tester import (
    StrategyRule, 
    run_strategy_test, 
    DESIGN_SEASONS, 
    HOLDOUT_SEASONS
)
from edgescout.config import DEFAULT_DB_PATH


def test_holdout_and_design_splits_definition():
    """
    User requirement:
    'Default split: design on seasons 2012/13-2019/20, hold out 2020/21-2024/25.'
    """
    assert DESIGN_SEASONS == ['1213', '1314', '1415', '1516', '1617', '1718', '1819', '1920']
    assert len(DESIGN_SEASONS) == 8

    assert HOLDOUT_SEASONS == ['2021', '2122', '2223', '2324', '2425']
    assert len(HOLDOUT_SEASONS) == 5


def test_strategy_test_execution_and_trial_persistence():
    """
    Executes a rule and verifies:
    1. Both design and holdout stats are computed.
    2. Holdout is headlined.
    3. Trial counter is persisted in SQLite `strategy_trials` table.
    4. Multiple-testing warning scales with trial count.
    """
    rule = StrategyRule(
        name="Test Home Favs",
        role_filter="FAVOURITE",
        selections=["H"]
    )
    res = run_strategy_test(rule, db_path=str(DEFAULT_DB_PATH), log_trial=True)

    assert res['headlined_split'] == 'HOLDOUT (2020/21 – 2024/25)'
    assert 'holdout' in res
    assert 'design' in res

    # Holdout bets + Design bets must equal overall bets
    assert res['holdout']['total_bets'] + res['design']['total_bets'] == res['overall']['total_bets']
    assert res['holdout']['total_bets'] > 0
    assert res['design']['total_bets'] > 0

    # Multiple testing warning
    assert res['total_trials_run'] >= 1
    assert "Multiple-Testing Notice" in res['multiple_testing_warning']
    assert res['expected_false_positives'] >= 0.05

    # Check database persistence directly
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM strategy_trials;")
    count = cur.fetchone()[0]
    assert count >= 1

    cur.execute("SELECT rule_description, holdout_bets, verdict FROM strategy_trials ORDER BY trial_id DESC LIMIT 1;")
    row = cur.fetchone()
    assert row[0] == "Test Home Favs"
    assert row[1] == res['holdout']['total_bets']
    assert "MARGIN" in row[2] or "ANOMALY" in row[2] or "WORSE" in row[2]
    conn.close()


def test_verdict_indistinguishable_from_margin():
    """
    Verifies that when holdout CI covers the margin baseline, verdict is 'INDISTINGUISHABLE FROM THE MARGIN'.
    """
    rule = StrategyRule(
        name="Home Favourites",
        role_filter="FAVOURITE",
        selections=["H"]
    )
    res = run_strategy_test(rule, db_path=str(DEFAULT_DB_PATH), log_trial=False)
    assert "INDISTINGUISHABLE FROM THE MARGIN" in res['verdict']
