"""
Unit tests for Real Settlement, Stable ID Matching, Void Stake Refunds, and CLV Tracking.
"""
import pytest
import sqlite3
import tempfile
from pathlib import Path

from edgescout.ledger import PaperLedger


@pytest.fixture
def temp_ledger():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        db_path = str(Path(tmpdir) / "test_ledger.sqlite3")
        ledger = PaperLedger(db_path=db_path)
        yield ledger


def test_auto_settle_real_feed_stable_ids(temp_ledger):
    """
    Tests auto-settlement matching stable match IDs from football-data.org.
    """
    # Place two bets on distinct stable match IDs
    b1 = temp_ledger.place_bet(
        idempotency_key="idemp_real_1",
        match_id="fd_5001",
        match_name="Arsenal vs Chelsea",
        league_code="PL",
        selection="H",
        odds=2.00,
        stake=1000.0
    )
    b2 = temp_ledger.place_bet(
        idempotency_key="idemp_real_2",
        match_id="fd_5002",
        match_name="Man City vs Liverpool",
        league_code="PL",
        selection="D",
        odds=3.50,
        stake=1000.0
    )

    # Simulated feed with real results mapped strictly by stable match ID
    feed = {
        "fd_5001": {"status": "FINISHED", "ftr": "H", "closing_odds": 1.90}, # Bet 1 WON
        "fd_5002": {"status": "FINISHED", "ftr": "A", "closing_odds": 3.60}  # Bet 2 LOST
    }

    res = temp_ledger.auto_settle_from_results(feed)
    assert res['settled_count'] == 2
    assert res['void_count'] == 0

    summary = temp_ledger.get_ledger_summary()
    assert summary['total_settled_bets'] == 2
    # P/L: +1000 (from b1) - 1000 (from b2) = 0
    assert summary['net_profit_loss'] == 0.0

    # Verify CLV was calculated on b1: (2.00 / 1.90) - 1 = +0.0526 (5.26%)
    settled_bets = summary['recent_bets']
    bet1_settled = next(b for b in settled_bets if b['id'] == b1['bet_id'])
    assert bet1_settled['status'] == 'WON'
    assert bet1_settled['closing_odds'] == 1.90
    assert pytest.approx(bet1_settled['clv'], rel=1e-2) == 0.0526


def test_void_match_refunds_full_stake(temp_ledger):
    """
    User requirement:
    'Handle postponed/void games (stake refunded).'
    """
    initial_bk = temp_ledger.get_bankroll()['current_bankroll']
    assert initial_bk == 100000.0

    b = temp_ledger.place_bet(
        idempotency_key="idemp_void_1",
        match_id="fd_5003",
        match_name="Bayern vs Dortmund",
        league_code="BL1",
        selection="H",
        odds=1.50,
        stake=1000.0
    )
    # Bankroll was deducted by 1000
    assert temp_ledger.get_bankroll()['current_bankroll'] == 99000.0

    # Match was POSTPONED
    feed = {
        "fd_5003": {"status": "POSTPONED"}
    }
    res = temp_ledger.auto_settle_from_results(feed)
    assert res['void_count'] == 1

    # Bankroll MUST be refunded the full 1,000 back to 100,000!
    assert temp_ledger.get_bankroll()['current_bankroll'] == 100000.0

    summary = temp_ledger.get_ledger_summary()
    assert summary['total_void_bets'] == 1
    assert summary['net_profit_loss'] == 0.0


def test_manual_settle_override_with_clv(temp_ledger):
    """
    User requirement:
    'add manual settle (W/L/void) for leagues the free tier doesn't cover... allow optional closing odds entry for a CLV column.'
    """
    b = temp_ledger.place_bet(
        idempotency_key="idemp_manual_1",
        match_id="custom_nigerian_league_1",
        match_name="Enyimba vs Kano Pillars",
        league_code="NPFL",
        selection="H",
        odds=2.20,
        stake=2000.0
    )
    assert temp_ledger.get_bankroll()['current_bankroll'] == 98000.0

    # User manually settles as WON with closing odds 2.00
    res = temp_ledger.manual_settle_bet(
        bet_id=b['bet_id'],
        outcome="WON",
        closing_odds=2.00
    )
    assert res['status'] == "WON"
    assert res['profit_loss'] == 2400.0 # 2000 * 2.20 - 2000 = 2400
    # CLV: (2.20 / 2.00) - 1 = +0.10 (+10%)
    assert res['clv'] == 0.10

    # Bankroll credited with payout 4,400 -> 98,000 + 4,400 = 102,400
    assert temp_ledger.get_bankroll()['current_bankroll'] == 102400.0

