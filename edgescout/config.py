"""
Configuration module for EdgeScout.
Stores model parameters, free-tier rate limits, staking rules, and league mappings.
"""
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Dict, List, Tuple

# Base Directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"
REPORTS_DIR = BASE_DIR / "reports"
PLOTS_DIR = REPORTS_DIR / "plots"

for path in [DATA_DIR, RAW_DATA_DIR, CACHE_DIR, REPORTS_DIR, PLOTS_DIR]:
    path.mkdir(parents=True, exist_ok=True)

# Database
DEFAULT_DB_PATH = DATA_DIR / "edgescout.sqlite3"

# Supported Leagues
LEAGUE_CODES = {
    "EPL": "E0",           # English Premier League
    "LA_LIGA": "SP1",      # Spanish Primera Division
    "SERIE_A": "I1",       # Italian Serie A
    "BUNDESLIGA": "D1",    # German Bundesliga 1
    "LIGUE_1": "F1",       # French Ligue 1
    "CHAMPIONS_LEAGUE": "CL" # UEFA Champions League
}

LEAGUE_NAMES = {
    "E0": "English Premier League",
    "SP1": "Spanish La Liga",
    "I1": "Italian Serie A",
    "D1": "German Bundesliga",
    "F1": "French Ligue 1",
    "CL": "UEFA Champions League"
}

# Free-Tier API Rate Limits Specification
FREE_TIER_LIMITS = {
    "football-data.co.uk": {
        "rate_limit": "Unmetered CSV archives",
        "monthly_quota": "Unlimited",
        "description": "Historical matches, half-time, full-time scores, opening and closing odds",
        "auth_required": False
    },
    "football-data.org": {
        "rate_limit": "10 calls / min",
        "monthly_quota": "Unmetered under 10/min (100 req/24h for unauthenticated)",
        "description": "Fixtures, live results, standings for 12 tier-one competitions",
        "auth_required": True
    },
    "API-Football": {
        "rate_limit": "10 calls / min, 100 req / day",
        "monthly_quota": "3,000 req / month (100/day reset at 00:00 UTC)",
        "description": "Lineups, injuries, squad news (requires strict budgeter)",
        "auth_required": True
    },
    "OddsPapi": {
        "rate_limit": "100 calls / hour",
        "monthly_quota": "250 req / month (legacy free tier; paused for new accounts)",
        "description": "Bookmaker odds including SportyBet (only query shortlisted EV bets)",
        "auth_required": True
    },
    "The Odds API": {
        "rate_limit": "500 credits / month",
        "monthly_quota": "500 credits / month (each call costs markets × regions)",
        "description": "Global sharp and soft bookmakers odds aggregation",
        "auth_required": True
    }
}

# Staking & Bankroll Settings (Phase 2 & Paper Trading)
class StakingConfig(BaseModel):
    kelly_fraction: float = Field(0.25, description="Quarter-Kelly multiplier")
    max_bet_fraction: float = Field(0.02, description="Max 2% of bankroll per single bet")
    max_daily_exposure: float = Field(0.06, description="Max 6% total bankroll exposed per day")
    min_edge: float = Field(0.02, description="Minimum +EV edge required to bet (2%)")
    default_bankroll: float = Field(100_000.0, description="Default virtual bankroll (in currency units, e.g. NGN)")

# Tier Classification Thresholds
class TierThresholds(BaseModel):
    high_confidence_prob: float = 0.55
    high_confidence_edge: float = 0.05
    value_edge: float = 0.03
    longshot_min_odds: float = 5.0
    longshot_fixed_stake_fraction: float = 0.005 # 0.5% bankroll cap for longshots

# Backtest Default Parameters: 13 seasons from 2012/13 to 2024/25
EXTENDED_SEASONS = [
    "1213", "1314", "1415", "1516", "1617", 
    "1718", "1819", "1920", "2021", "2122", 
    "2223", "2324", "2425"
]
BURN_IN_SEASONS = ["1213", "1314"] # 2 full burn-in seasons before evaluation
DEFAULT_SEASONS = EXTENDED_SEASONS
DEFAULT_EDGE_THRESHOLDS = [0.02, 0.03, 0.05, 0.08, 0.10]

