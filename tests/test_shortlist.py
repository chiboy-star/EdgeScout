"""
Unit tests for EdgeScout Phase 4 Suggestion Shortlist Engine.
Verifies:
1. Shortlist ranking strictly by lowest expected cost.
2. Tier classification (Steady >=55%, Balanced 35-55%, Long shot <20%) and max 3 cap.
3. Long-shot stake cap (hard 0.25% of bankroll).
4. Empty tier handling.
5. Idempotency key protection in paper ledger.
6. Honesty label: "Lowest-cost pick, not a prediction of profit."
"""
import pytest
import sqlite3
import uuid
import tempfile
from pathlib import Path

from edgescout.config import DEFAULT_DB_PATH
from edgescout.shortlist import generate_suggestion_shortlist
from edgescout.ledger import PaperLedger


def test_shortlist_generation_and_tiers():
    bankroll = 100000.0
    res = generate_suggestion_shortlist(str(DEFAULT_DB_PATH), bankroll=bankroll)
    
    assert "tiers" in res
    assert "summary" in res
    tiers = res["tiers"]
    
    assert "Steady" in tiers
    assert "Balanced" in tiers
    assert "Long shot" in tiers
    
    # Verify max 3 per tier
    for t_name, picks in tiers.items():
        assert len(picks) <= 3, f"Tier {t_name} exceeded 3 picks: found {len(picks)}"


def test_shortlist_ranking_by_lowest_expected_cost():
    bankroll = 50000.0
    res = generate_suggestion_shortlist(str(DEFAULT_DB_PATH), bankroll=bankroll)
    tiers = res["tiers"]
    
    for t_name, picks in tiers.items():
        if len(picks) > 1:
            for i in range(len(picks) - 1):
                c1 = picks[i]
                c2 = picks[i + 1]
                assert c1["expected_cost_per_1000"] <= c2["expected_cost_per_1000"], (
                    f"Tier {t_name} not sorted by lowest expected cost: "
                    f"{c1['expected_cost_per_1000']} > {c2['expected_cost_per_1000']}"
                )


def test_tier_probability_boundaries():
    res = generate_suggestion_shortlist(str(DEFAULT_DB_PATH), bankroll=100000.0)
    tiers = res["tiers"]
    
    for pick in tiers["Steady"]:
        assert pick["shin_market_prob_pct"] >= 55.0, f"Steady pick prob < 55%: {pick['shin_market_prob_pct']}%"
        
    for pick in tiers["Balanced"]:
        assert 35.0 <= pick["shin_market_prob_pct"] < 55.0, f"Balanced pick out of range: {pick['shin_market_prob_pct']}%"
        
    for pick in tiers["Long shot"]:
        assert pick["shin_market_prob_pct"] < 20.0, f"Long shot pick prob >= 20%: {pick['shin_market_prob_pct']}%"


def test_long_shot_hard_stake_cap():
    bankroll = 200000.0
    res = generate_suggestion_shortlist(str(DEFAULT_DB_PATH), bankroll=bankroll)
    longshots = res["tiers"]["Long shot"]
    
    max_allowed_stake = bankroll * 0.0025 # 0.25% hard cap
    
    for pick in longshots:
        assert pick["stake_cap_pct"] <= 0.25, f"Long shot stake cap pct exceeded 0.25%: {pick['stake_cap_pct']}"
        assert pick["suggested_stake"] <= max_allowed_stake + 0.01, (
            f"Long shot stake {pick['suggested_stake']} exceeds 0.25% cap ({max_allowed_stake})"
        )


def test_honesty_labels_present():
    res = generate_suggestion_shortlist(str(DEFAULT_DB_PATH), bankroll=100000.0)
    expected_label = "Lowest-cost pick, not a prediction of profit."
    
    assert res["summary"]["label"] == expected_label
    
    for t_name, picks in res["tiers"].items():
        for pick in picks:
            assert pick["pick_label"] == expected_label
            # Odds source must distinguish reference from SportyBet
            assert "NOT SportyBet" in pick["odds_source"]


def test_shortlist_idempotency_integration():
    with tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False) as tmp:
        db_path = tmp.name
        
    ledger = PaperLedger(db_path)
    res = generate_suggestion_shortlist(str(DEFAULT_DB_PATH), bankroll=100000.0)
    
    # Pick first available candidate across tiers
    candidate = None
    for picks in res["tiers"].values():
        if picks:
            candidate = picks[0]
            break
            
    assert candidate is not None
    
    idemp_key = f"test_idemp_{uuid.uuid4()}"
    
    # First bet placement
    p1 = ledger.place_bet(
        idempotency_key=idemp_key,
        match_id=candidate["match_id"],
        match_name=candidate["match_name"],
        league_code=candidate["league_code"],
        selection=candidate["selection"],
        odds=candidate["odds_taken"],
        stake=candidate["suggested_stake"]
    )
    assert p1["status"] == "PLACED"
    
    bk1 = ledger.get_bankroll()["current_bankroll"]
    expected_bk = 100000.0 - candidate["suggested_stake"]
    assert pytest.approx(bk1, 0.01) == expected_bk
    
    # Second bet placement with identical idempotency key (double tap)
    p2 = ledger.place_bet(
        idempotency_key=idemp_key,
        match_id=candidate["match_id"],
        match_name=candidate["match_name"],
        league_code=candidate["league_code"],
        selection=candidate["selection"],
        odds=candidate["odds_taken"],
        stake=candidate["suggested_stake"]
    )
    assert p2["status"] == "ALREADY_EXISTS"
    assert p2["bet_id"] == p1["bet_id"]
    
    # Verify bankroll was not double debited
    bk2 = ledger.get_bankroll()["current_bankroll"]
    assert pytest.approx(bk2, 0.01) == bk1
    
    # Clean up
    try:
        Path(db_path).unlink(missing_ok=True)
    except Exception:
        pass

