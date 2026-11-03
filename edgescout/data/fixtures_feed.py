"""
Fixtures Feed & Real Data Provenance Engine for EdgeScout Phase 4.4.
Enforces 100% REAL DATA from verified sources:
1. football-data.co.uk fixtures.csv (live bookmaker pre-match odds)
2. api.football-data.org v4 matches (Tier One schedule: Champions League, Premier League, Championship, etc.)
3. SQLite custom_fixtures (user manual entries)

Strictly NO hardcoded demo fixtures. Every fixture carries an auditable source tag.
"""
import io
import os
import time
import json
import sqlite3
import requests
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

from edgescout.config import DEFAULT_DB_PATH, CACHE_DIR
from edgescout.dates import (
    parse_kickoff_to_utc,
    format_wat,
    format_countdown,
    is_upcoming_fixture,
    get_now_utc
)

FIXTURES_CSV_URL = "https://www.football-data.co.uk/fixtures.csv"
FIXTURES_CACHE_FILE = CACHE_DIR / "fixtures_co_uk.csv"
FIXTURES_META_FILE = CACHE_DIR / "fixtures_meta.json"
FD_ORG_CACHE_FILE = CACHE_DIR / "football_data_org_7d.json"

# Competition display names
LEAGUE_DIV_MAP = {
    'E0': 'Premier League',
    'E1': 'Championship',
    'E2': 'League One',
    'E3': 'League Two',
    'SP1': 'La Liga',
    'I1': 'Serie A',
    'D1': 'Bundesliga',
    'F1': 'Ligue 1',
    'B1': 'Belgian First Division',
    'N1': 'Dutch Eredivisie',
    'P1': 'Primeira Liga',
    'CL': 'UEFA Champions League',
    'CUSTOM': 'Custom Competition'
}

FD_ORG_COMP_MAP = {
    'CL': ('CL', 'UEFA Champions League'),
    'ELC': ('E1', 'Championship'),
    'PL': ('E0', 'Premier League'),
    'PD': ('SP1', 'La Liga'),
    'SA': ('I1', 'Serie A'),
    'BL1': ('D1', 'Bundesliga'),
    'FL1': ('F1', 'Ligue 1'),
    'DED': ('N1', 'Dutch Eredivisie'),
    'PPL': ('P1', 'Primeira Liga'),
    'BSA': ('BSA', 'Campeonato Brasileiro')
}


def init_custom_fixtures_table(db_path: Path = DEFAULT_DB_PATH):
    """Initializes table for user-entered custom fixtures and odds."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_fixtures (
            id TEXT PRIMARY KEY,
            match_name TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            league TEXT NOT NULL,
            league_code TEXT NOT NULL,
            kickoff_utc TEXT NOT NULL,
            home_odds REAL NOT NULL,
            draw_odds REAL NOT NULL,
            away_odds REAL NOT NULL,
            source TEXT NOT NULL DEFAULT 'manual_entry',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()


def fetch_football_data_co_uk_csv() -> Tuple[pd.DataFrame, str]:
    """
    Downloads real fixtures.csv from football-data.co.uk.
    Returns DataFrame and ISO timestamp of fetch.
    """
    fetch_time_str = datetime.now(timezone.utc).isoformat()
    try:
        session = requests.Session()
        session.trust_env = False
        resp = session.get(FIXTURES_CSV_URL, timeout=10)
        if resp.status_code == 200 and len(resp.content) > 100:
            df = pd.read_csv(io.BytesIO(resp.content))
            df.columns = [c.replace('\ufeff', '').strip() for c in df.columns]
            # Save raw file and metadata
            df.to_csv(FIXTURES_CACHE_FILE, index=False)
            with open(FIXTURES_META_FILE, 'w', encoding='utf-8') as f:
                json.dump({'fetched_at': fetch_time_str, 'rows': len(df)}, f)
            return df, fetch_time_str
    except Exception as e:
        print(f"Notice: live fixtures.csv fetch error ({e}); attempting cache.")

    if FIXTURES_CACHE_FILE.exists():
        try:
            df = pd.read_csv(FIXTURES_CACHE_FILE)
            if FIXTURES_META_FILE.exists():
                with open(FIXTURES_META_FILE, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    fetch_time_str = meta.get('fetched_at', fetch_time_str)
            return df, fetch_time_str
        except Exception:
            pass

    return pd.DataFrame(), fetch_time_str


def fetch_football_data_org_matches() -> Tuple[List[Dict[str, Any]], str]:
    """
    Fetches scheduled matches from api.football-data.org (Tier One: CL, PL, ELC, PD, SA, etc.)
    for the next 7 days.
    """
    key = os.getenv('FOOTBALL_DATA_ORG_KEY') or os.getenv('FOOTBALL_DATA_KEY')
    fetch_time_str = datetime.now(timezone.utc).isoformat()
    if not key or not key.strip():
        # Check cache
        if FD_ORG_CACHE_FILE.exists():
            try:
                with open(FD_ORG_CACHE_FILE, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                    return cached.get('matches', []), cached.get('fetched_at', fetch_time_str)
            except Exception:
                pass
        return [], fetch_time_str

    now_utc = get_now_utc()
    date_from = now_utc.strftime('%Y-%m-%d')
    date_to = (now_utc + timedelta(days=7)).strftime('%Y-%m-%d')

    # If cache is fresh (< 15 mins), use it
    if FD_ORG_CACHE_FILE.exists():
        try:
            mtime = FD_ORG_CACHE_FILE.stat().st_mtime
            if time.time() - mtime < 900: # 15 minutes
                with open(FD_ORG_CACHE_FILE, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                    return cached.get('matches', []), cached.get('fetched_at', fetch_time_str)
        except Exception:
            pass

    try:
        session = requests.Session()
        session.trust_env = False
        headers = {'X-Auth-Token': key.strip()}
        url = f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}"
        resp = session.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            matches = data.get('matches', [])
            with open(FD_ORG_CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump({'matches': matches, 'fetched_at': fetch_time_str}, f)
            return matches, fetch_time_str
    except Exception as e:
        print(f"Notice: football-data.org fetch error ({e}); using cache.")

    if FD_ORG_CACHE_FILE.exists():
        try:
            with open(FD_ORG_CACHE_FILE, 'r', encoding='utf-8') as f:
                cached = json.load(f)
                return cached.get('matches', []), cached.get('fetched_at', fetch_time_str)
        except Exception:
            pass

    return [], fetch_time_str


def get_custom_fixtures(db_path: Path = DEFAULT_DB_PATH) -> List[Dict[str, Any]]:
    """Loads user-added custom fixtures from SQLite."""
    init_custom_fixtures_table(db_path)
    fixtures = []
    now_utc = get_now_utc()
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM custom_fixtures ORDER BY kickoff_utc ASC;").fetchall()
            for r in rows:
                k_utc = r['kickoff_utc']
                try:
                    dt = datetime.fromisoformat(k_utc.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    # Filter out matches in the past
                    if dt < now_utc + timedelta(minutes=10):
                        continue
                except Exception:
                    continue

                fixtures.append({
                    'id': r['id'],
                    'match_name': r['match_name'],
                    'home_team': r['home_team'],
                    'away_team': r['away_team'],
                    'league': r['league'],
                    'league_code': r['league_code'],
                    'kickoff_utc': dt.isoformat(),
                    'home_odds': r['home_odds'],
                    'draw_odds': r['draw_odds'],
                    'away_odds': r['away_odds'],
                    'source': "manual_entry",
                    'is_custom': True
                })
    except Exception as e:
        print(f"Notice: loading custom fixtures error ({e})")
    return fixtures


def add_custom_fixture(
    match_name: str,
    home_team: str,
    away_team: str,
    league: str,
    kickoff_utc: str,
    home_odds: float,
    draw_odds: float,
    away_odds: float,
    db_path: Path = DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """Saves a custom fixture and odds into SQLite."""
    init_custom_fixtures_table(db_path)
    fix_id = f"custom_fix_{int(time.time())}_{abs(hash(match_name)) % 10000}"
    league_code = "CUSTOM"
    for div_c, div_name in LEAGUE_DIV_MAP.items():
        if div_name.lower() in league.lower():
            league_code = div_c
            break

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
        INSERT INTO custom_fixtures (id, match_name, home_team, away_team, league, league_code, kickoff_utc, home_odds, draw_odds, away_odds, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual_entry');
        """, (fix_id, match_name, home_team, away_team, league, league_code, kickoff_utc, home_odds, draw_odds, away_odds))
        conn.commit()

    return {
        'id': fix_id,
        'match_name': match_name,
        'home_team': home_team,
        'away_team': away_team,
        'league': league,
        'league_code': league_code,
        'kickoff_utc': kickoff_utc,
        'home_odds': home_odds,
        'draw_odds': draw_odds,
        'away_odds': away_odds,
        'source': "manual_entry"
    }


def get_data_health_stats(db_path: Path = DEFAULT_DB_PATH) -> Dict[str, Any]:
    """
    Computes all fields for Data Health Strip and Phase 4.4 Data Provenance:
    - Raw row count of fixtures.csv
    - Rows per league in fixtures.csv
    - Coverage breakdown (CL, PL, ELC, PD, SA, etc.)
    - Missing competitions explanation
    - Latest DB match date and upcoming matches count
    """
    # 1. DB history stats
    latest_db_date = "Unknown"
    total_db_matches = 0
    db_p = Path(db_path) if db_path else Path("data/edgescout.db")
    if db_p.exists():
        try:
            with sqlite3.connect(db_p) as conn:
                row = conn.execute("SELECT MAX(match_date), COUNT(*) FROM matches;").fetchone()
                if row and row[0]:
                    dt_db = datetime.strptime(row[0], "%Y-%m-%d")
                    latest_db_date = f"{dt_db.day} {dt_db.strftime('%b %Y')}"
                    total_db_matches = row[1]
        except Exception:
            pass

    # 2. fixtures.csv stats
    csv_rows_count = 0
    csv_league_breakdown = {}
    csv_fetch_time = "Unknown"
    is_stale = False
    age_hours = 0.0

    if FIXTURES_CACHE_FILE.exists():
        try:
            df = pd.read_csv(FIXTURES_CACHE_FILE)
            csv_rows_count = len(df)
            if 'Div' in df.columns:
                for div, count in df['Div'].value_counts().items():
                    name = LEAGUE_DIV_MAP.get(str(div), str(div))
                    csv_league_breakdown[name] = int(count)

            mtime = FIXTURES_CACHE_FILE.stat().st_mtime
            age_sec = time.time() - mtime
            age_hours = round(age_sec / 3600.0, 1)
            is_stale = age_sec > 86400
            fetch_dt = datetime.fromtimestamp(mtime, timezone.utc)
            csv_fetch_time = fetch_dt.strftime('%H:%M UTC')
        except Exception:
            pass

    # 3. football-data.org stats
    fd_key_set = bool(os.getenv('FOOTBALL_DATA_ORG_KEY') or os.getenv('FOOTBALL_DATA_KEY'))
    fd_matches_count = 0
    fd_comp_breakdown = {}
    if FD_ORG_CACHE_FILE.exists():
        try:
            with open(FD_ORG_CACHE_FILE, 'r', encoding='utf-8') as f:
                fd_data = json.load(f)
                matches = fd_data.get('matches', [])
                fd_matches_count = len(matches)
                for m in matches:
                    c_name = m.get('competition', {}).get('name', 'Unknown')
                    fd_comp_breakdown[c_name] = fd_comp_breakdown.get(c_name, 0) + 1
        except Exception:
            pass

    # 4. Custom fixtures count
    custom_count = len(get_custom_fixtures(db_path))

    # Explanation of coverage & missing competitions
    coverage_explanation = (
        f"fixtures.csv contains {csv_rows_count} matches for the active midweek slate. "
        "football-data.co.uk updates on a rolling basis; major weekend league odds (Premier League, La Liga, Serie A, Bundesliga) are published on Thursday/Friday. "
        + (f"football-data.org provides {fd_matches_count} upcoming 7-day fixtures (including UEFA Champions League). " if fd_key_set else "football-data.org API key not configured. ")
        + "Note: UEFA Europa League (EL) and Conference League (ECL) are restricted to paid tiers on football-data.org. Use the manual 'Add Fixture' form to enter any match."
    )

    return {
        'latest_match_date': latest_db_date,
        'total_db_matches': total_db_matches,
        'fixtures_csv_rows': csv_rows_count,
        'fixtures_csv_leagues': csv_league_breakdown,
        'fixtures_fetch_time_label': csv_fetch_time,
        'is_stale': is_stale,
        'age_hours': age_hours,
        'football_data_org_key_set': fd_key_set,
        'football_data_org_matches': fd_matches_count,
        'football_data_org_leagues': fd_comp_breakdown,
        'custom_fixtures_count': custom_count,
        'missing_competitions': [
            'UEFA Europa League (Tier 3/paid on football-data.org)',
            'UEFA Europa Conference League (Tier 3/paid on football-data.org)',
            'Domestic cups (FA Cup, Copa del Rey, DFB-Pokal)'
        ],
        'coverage_explanation': coverage_explanation
    }
