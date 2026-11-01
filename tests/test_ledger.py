"""
Unit tests for Paper Ledger:
- Idempotency & double-tap protection
- Bankroll tracking
- Sizing rules (flat 1% default, user prob Kelly, 2% single cap, 6% daily cap)
- Undo functionality
- Settlement (WON / LOST)
- Sample size warning (< 300 bets)
"""
import pytest
import tempfile
from pathlib import Path

from edgescout.ledger import PaperLedger


@pytest.fixture
def temp_ledger():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        temp_path = str(Path(temp_dir) / "test_ledger.sqlite3")
        ledger = PaperLedger(db_path=temp_path)
        yield ledger


def test_idempotency_prevents_duplicate_bets(temp_ledger):
    idemp_key = "test_key_001"
    
    # Place bet 1
    res1 = temp_ledger.place_bet(
        idempotency_key=idemp_key,
        match_id="m1",
        match_name="Arsenal vs Chelsea",
        league_code="E0",
        selection="H",
        odds=2.0,
        stake=1000.0
    )
    assert res1['status'] == 'PLACED'
    bk_after_first = temp_ledger.get_bankroll()['current_bankroll']
    assert bk_after_first == 99000.0

    # Place bet 2 with the EXACT same idempotency key (double tap simulation)
    res2 = temp_ledger.place_bet(
        idempotency_key=idemp_key,
        match_id="m1",
        match_name="Arsenal vs Chelsea",
        league_code="E0",
        selection="H",
        odds=2.0,
        stake=1000.0
    )
    assert res2['status'] == 'ALREADY_EXISTS'
    # Bankroll must NOT be deducted twice!
    bk_after_second = temp_ledger.get_bankroll()['current_bankroll']
    assert bk_after_second == 99000.0


def test_undo_bet_refunds_bankroll(temp_ledger):
    res = temp_ledger.place_bet(
        idempotency_key="undo_key_1",
        match_id="m2",
        match_name="Man City vs Liverpool",
        league_code="E0",
        selection="D",
        odds=3.5,
        stake=2000.0
    )
    assert temp_ledger.get_bankroll()['current_bankroll'] == 98000.0

    undo_res = temp_ledger.undo_bet(res['bet_id'])
    assert undo_res['status'] == 'UNDONE'
    # Bankroll should be restored
    assert temp_ledger.get_bankroll()['current_bankroll'] == 100000.0


def test_settlement_won_and_lost(temp_ledger):
    # Bet 1: Will win
    b1 = temp_ledger.place_bet("k_won", "m3", "Bayern vs Dortmund", "D1", "H", odds=2.0, stake=1000.0)
    # Bet 2: Will lose
    b2 = temp_ledger.place_bet("k_lost", "m4", "Inter vs Milan", "I1", "A", odds=3.0, stake=1000.0)

    # Settle Bet 1 (Won)
    s1 = temp_ledger.settle_bet(b1['bet_id'], actual_result="H", closing_odds=1.90)
    assert s1['status'] == 'WON'
    assert s1['profit_loss'] == 1000.0

    # Settle Bet 2 (Lost)
    s2 = temp_ledger.settle_bet(b2['bet_id'], actual_result="H", closing_odds=3.20)
    assert s2['status'] == 'LOST'
    assert s2['profit_loss'] == -1000.0

    # Bankroll: 100k - 2k + 2k (won payout) = 100,000
    assert temp_ledger.get_bankroll()['current_bankroll'] == 100000.0


def test_sample_size_warning_flag(temp_ledger):
    # With 0 or few bets, sample warning must be True
    summary = temp_ledger.get_ledger_summary()
    assert summary['sample_warning']['has_warning'] is True
    assert "sample size too small to judge" in summary['sample_warning']['message'].lower()
    assert summary['sample_warning']['settled_count'] == 0
    assert summary['sample_warning']['target_count'] == 300


def test_stake_suggestion_rules(temp_ledger):
    # Default without user probability -> Flat 1%
    sug_flat = temp_ledger.calculate_suggested_stake(odds=2.0)
    assert sug_flat['method'].startswith("Flat 1%")
    assert sug_flat['suggested_stake'] == 1000.0 # 1% of 100,000

    # With user probability estimate -> Quarter-Kelly capped at 2%
    sug_kelly = temp_ledger.calculate_suggested_stake(odds=2.0, user_prob=0.80)
    assert "Kelly" in sug_kelly['method']
    assert sug_kelly['suggested_stake'] == 2000.0 # Capped at 2%

