"""
FastAPI Backend for EdgeScout.
Provides clean async REST JSON endpoints for:
- /api/shortlist (Ranked Lowest-Cost Suggestions by Tier)
- /api/fixtures (Today & This Week Market View)
- /api/bets (Paper Ledger & Performance Summary)
- /api/bets/place (Disciplined Bet Placement with Idempotency)
- /api/bets/undo (6-second Undo)
- /api/settle/auto (Real football-data.org Results Settlement)
- /api/settle/manual (Manual Override W/L/Void with Closing Odds CLV)
- /api/accumulator (Audited Accumulator Compounding Overround)
- /api/strategy/run (13-Season Tester with Design vs Holdout Split & Trials Log)
- /api/strategy/trials (List Past Strategy Trials)
- /api/bankroll/reset (Reset Bankroll to ₦100,000)
"""
import sqlite3
from typing import Dict, List, Optional, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Body, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from edgescout.config import DEFAULT_DB_PATH, BASE_DIR
from edgescout.ledger import PaperLedger
from edgescout.fixtures import get_market_fixtures
from edgescout.shortlist import generate_suggestion_shortlist
from edgescout.data.football_data_org import FootballDataOrgClient
from edgescout.accumulator import calculate_accumulator
from edgescout.strategy_tester import StrategyRule, run_strategy_test
from edgescout.data.fixtures_feed import (
    get_data_health_stats,
    fetch_football_data_co_uk_csv,
    add_custom_fixture,
    get_custom_fixtures
)

app = FastAPI(
    title="EdgeScout API",
    description="Football Price-Discipline, Shortlist & Paper-Trading Engine",
    version="4.0.0"
)

# Enable CORS for Next.js development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ledger = PaperLedger(str(DEFAULT_DB_PATH))


# -------------------------------------------------------------------------
# Request Models
# -------------------------------------------------------------------------
class AddCustomFixtureRequest(BaseModel):
    match_name: str = Field(..., description="e.g. Arsenal vs Chelsea")
    home_team: Optional[str] = None
    away_team: Optional[str] = None
    league: str = Field("Custom League", description="e.g. Premier League or UEFA Champions League")
    kickoff_utc: str = Field(..., description="ISO format UTC kickoff timestamp")
    home_odds: float = Field(..., gt=1.0)
    draw_odds: float = Field(..., gt=1.0)
    away_odds: float = Field(..., gt=1.0)


class PlaceBetRequest(BaseModel):
    idempotency_key: str = Field(..., description="Unique client key to prevent double submits")
    match_id: str = Field(..., description="Stable match ID")
    match_name: str = Field(..., description="e.g. Arsenal vs Chelsea")
    league_code: str = Field("CUSTOM", description="e.g. E0, SP1")
    selection: str = Field("H", description="'H', 'D', 'A'")
    odds: float = Field(..., gt=1.0, description="Decimal odds taken")
    stake: Optional[float] = Field(None, gt=0, description="Optional custom stake")
    user_prob: Optional[float] = Field(None, gt=0, lt=1, description="Optional user probability for Kelly")
    kickoff_utc: Optional[str] = Field(None, description="ISO format kickoff timestamp in UTC")


class UndoBetRequest(BaseModel):
    bet_id: str = Field(..., description="UUID of bet to undo")


class ManualSettleRequest(BaseModel):
    bet_id: str = Field(..., description="UUID of bet to settle")
    outcome: str = Field(..., description="'WON', 'LOST', or 'VOID'")
    closing_odds: Optional[float] = Field(None, gt=1.0, description="Optional closing price for CLV")


class AccumulatorLeg(BaseModel):
    match_id: Optional[str] = "custom_1"
    match_name: Optional[str] = "Match"
    selection: Optional[str] = "H"
    odds: float = Field(..., gt=1.0)
    market_odds_1x2: Optional[List[float]] = None


class AccumulatorRequest(BaseModel):
    legs: List[Dict[str, Any]] = Field(..., min_items=1)
    stake: float = Field(1000.0, gt=0)


class StrategyRunRequest(BaseModel):
    name: str = "Custom Rule"
    leagues: Optional[List[str]] = None
    min_odds: float = 1.01
    max_odds: float = 100.0
    selections: List[str] = ["H"]
    role_filter: str = "ALL"
    run_type: Optional[str] = "user"


class ResetBankrollRequest(BaseModel):
    amount: float = 100000.0


# -------------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------------

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "app": "EdgeScout",
        "version": "4.0.0",
        "disclaimer": "Lowest-cost picks, not a prediction of profit."
    }


@app.get("/api/shortlist")
def get_shortlist(
    bankroll: Optional[float] = Query(None, description="Current bankroll for stake suggestions"),
    timeframe: str = Query("today", description="'today' (<24h) or 'week' (next 7 days)")
):
    """
    Returns shortlist ranked by LOWEST expected cost in 3 tiers:
    Steady (prob >= 55%), Balanced (35-55%), Long shot (< 20%, capped at 0.25% stake).
    Enforces Phase 4.4 Rules:
    - Max 1 selection per match across entire shortlist.
    - If timeframe == 'today', strictly restricts to kickoff <= now + 24h.
    """
    if bankroll is None:
        bankroll = ledger.get_bankroll()["current_bankroll"]
    return generate_suggestion_shortlist(str(DEFAULT_DB_PATH), bankroll=bankroll, timeframe=timeframe)


@app.get("/api/fixtures")
def get_fixtures(force_refresh: bool = Query(False)):
    """Returns today and upcoming market fixtures with margin and cost metrics."""
    return {"fixtures": get_market_fixtures(force_refresh=force_refresh)}


@app.get("/api/bets")
def get_bets():
    """Returns complete paper ledger, bankroll, equity curve, and performance stats."""
    return ledger.get_ledger_summary()


@app.post("/api/fixtures/custom")
def create_custom_fixture(req: AddCustomFixtureRequest):
    """Adds a user-entered fixture and odds into SQLite custom_fixtures."""
    h_team = req.home_team or (req.match_name.split(" vs ")[0] if " vs " in req.match_name else req.match_name)
    a_team = req.away_team or (req.match_name.split(" vs ")[1] if " vs " in req.match_name else "Opponent")
    res = add_custom_fixture(
        match_name=req.match_name,
        home_team=h_team,
        away_team=a_team,
        league=req.league,
        kickoff_utc=req.kickoff_utc,
        home_odds=req.home_odds,
        draw_odds=req.draw_odds,
        away_odds=req.away_odds,
        db_path=DEFAULT_DB_PATH
    )
    return res


@app.get("/api/health/data")
def get_data_health():
    """Returns database and fixtures health metadata for top status strip."""
    return get_data_health_stats(DEFAULT_DB_PATH)


@app.post("/api/fixtures/refresh")
def refresh_fixtures():
    """Forces fresh re-download of fixtures.csv from football-data.co.uk and updates cache."""
    fetch_football_data_co_uk_csv()
    return get_data_health_stats(DEFAULT_DB_PATH)


@app.post("/api/bets/place")
def place_bet(req: PlaceBetRequest):
    """
    Places disciplined paper bet with idempotency check,
    1% flat default stake, 2% max bet cap, and 6% daily exposure cap.
    """
    stake = req.stake
    if stake is None:
        stake = ledger.suggest_stake(odds=req.odds, user_prob=req.user_prob)["suggested_stake"]

    res = ledger.place_bet(
        idempotency_key=req.idempotency_key,
        match_id=req.match_id,
        match_name=req.match_name,
        league_code=req.league_code,
        selection=req.selection,
        odds=req.odds,
        stake=stake,
        user_prob=req.user_prob,
        kickoff_utc=req.kickoff_utc
    )
    if res.get("status") == "ERROR":
        raise HTTPException(status_code=400, detail=res.get("message", "Error placing bet"))
    return res


@app.post("/api/bets/undo")
def undo_bet(req: UndoBetRequest):
    """Undo bet placement within 6 seconds."""
    res = ledger.undo_bet(req.bet_id)
    if res.get("status") == "ERROR":
        raise HTTPException(status_code=400, detail=res.get("message", "Unable to undo bet"))
    return res


@app.post("/api/settle/manual")
def manual_settle(req: ManualSettleRequest):
    """Manually settle a bet ('WON', 'LOST', 'VOID') with optional closing odds for CLV."""
    res = ledger.manual_settle_bet(
        bet_id=req.bet_id,
        outcome=req.outcome.upper(),
        closing_odds=req.closing_odds
    )
    if res.get("status") == "ERROR":
        raise HTTPException(status_code=400, detail=res.get("message", "Unable to settle bet"))
    return res


@app.post("/api/settle/auto")
def auto_settle():
    """Auto-settles bets from real football-data.org match results."""
    client = FootballDataOrgClient()
    results, is_demo = client.fetch_finished_results()
    res = ledger.auto_settle_from_results(results)
    res["is_demo_feed"] = is_demo
    return res


@app.post("/api/accumulator")
def analyze_accumulator(req: AccumulatorRequest):
    """Computes exact accumulator compounding overround 1 - 1/(1+M) and correlated leg checks."""
    return calculate_accumulator(req.legs, stake=req.stake)


@app.post("/api/strategy/run")
def run_strategy(req: StrategyRunRequest):
    """Executes rule across 13 seasons with Design (2012-2020) vs Holdout (2020-2025) split and trial logging."""
    rule = StrategyRule(
        name=req.name,
        leagues=req.leagues,
        min_odds=req.min_odds,
        max_odds=req.max_odds,
        selections=req.selections,
        role_filter=req.role_filter
    )
    return run_strategy_test(rule, run_type=req.run_type or "user")


@app.get("/api/strategy/trials")
def list_strategy_trials():
    """Returns trial counter and recent strategy test runs from SQLite (excluding agent test runs)."""
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM strategy_trials WHERE run_type != 'test';")
    count = cur.fetchone()[0]
    cur.execute("""
    SELECT trial_id, executed_at, rule_description, holdout_roi, holdout_ci_low, holdout_ci_high, verdict 
    FROM strategy_trials WHERE run_type != 'test' ORDER BY trial_id DESC LIMIT 20;
    """)
    recent = [
        {
            "id": r[0], "time": r[1], "rule": r[2], 
            "holdout_roi": r[3], "ci": (r[4], r[5]), "verdict": r[6]
        }
        for r in cur.fetchall()
    ]
    conn.close()
    return {"total_trials": count, "recent": recent}


@app.post("/api/bankroll/reset")
def reset_bankroll(req: ResetBankrollRequest = Body(default=ResetBankrollRequest())):
    """Resets paper ledger and bankroll."""
    ledger.reset_bankroll(req.amount)
    return {"status": "RESET", "bankroll": req.amount}


def run_server(port: int = 8000):
    import uvicorn
    print(f"EdgeScout FastAPI server running at http://127.0.0.1:{port}/")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == '__main__':
    run_server()
