"""
football-data.org Client & Settlement Feed for EdgeScout.
Respects free-tier rate limits (10 calls/minute), caches all raw JSON responses,
and maps matches to stable IDs for deterministic settlement.

If live feed cannot be reached or API key is not set, loads from local cache
or marks records with is_demo = True (never unlabeled).
"""
import os
import time
import json
import requests
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import deque

from edgescout.config import CACHE_DIR

FD_ORG_CACHE_DIR = CACHE_DIR / "football_data_org"
FD_ORG_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Free Tier competitions on football-data.org
COMPETITION_MAP = {
    'PL': 'Premier League',
    'PD': 'La Liga',
    'SA': 'Serie A',
    'BL1': 'Bundesliga',
    'FL1': 'Ligue 1',
    'CL': 'UEFA Champions League'
}


class FootballDataOrgClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        cache_dir: Path = FD_ORG_CACHE_DIR,
        rate_limit_per_min: int = 10
    ):
        self.api_key = api_key or os.environ.get('FOOTBALL_DATA_ORG_KEY') or os.environ.get('FOOTBALL_DATA_KEY')
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = "https://api.football-data.org/v4"
        self.rate_limit_per_min = rate_limit_per_min
        self.call_timestamps = deque()

    def _wait_for_rate_limit(self):
        """Enforces 10 calls per minute strict client-side limit."""
        now = time.time()
        while self.call_timestamps and now - self.call_timestamps[0] > 60:
            self.call_timestamps.popleft()
        if len(self.call_timestamps) >= self.rate_limit_per_min:
            sleep_time = 60.0 - (now - self.call_timestamps[0]) + 0.5
            if sleep_time > 0:
                time.sleep(sleep_time)
        self.call_timestamps.append(time.time())

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Makes rate-limited GET request with disk caching."""
        # Check cache first
        cache_key = f"{endpoint.replace('/', '_')}_{str(params)}.json"
        cache_file = self.cache_dir / cache_key
        
        # If cache exists and is less than 5 minutes old, return it
        if cache_file.exists():
            try:
                mtime = cache_file.stat().st_mtime
                if time.time() - mtime < 300: # 5 min fresh
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
            except Exception:
                pass

        if not self.api_key:
            return None

        self._wait_for_rate_limit()
        headers = {"X-Auth-Token": self.api_key}
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Save raw response to cache
                with open(cache_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                return data
            else:
                return None
        except Exception:
            return None

    def fetch_upcoming_fixtures(self, competitions: Optional[List[str]] = None) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Fetches scheduled/upcoming matches.
        Returns: (fixtures_list, is_demo)
        """
        comps = competitions or ['PL', 'PD', 'SA', 'BL1', 'FL1']
        all_fixtures = []
        is_live = False

        if self.api_key:
            for comp in comps:
                data = self._get(f"competitions/{comp}/matches", {'status': 'SCHEDULED,TIMED'})
                if data and 'matches' in data:
                    is_live = True
                    for m in data['matches']:
                        all_fixtures.append({
                            'match_id': f"fd_{m['id']}",
                            'fixture_id': m['id'],
                            'home_team': m.get('homeTeam', {}).get('name', 'Home Team'),
                            'away_team': m.get('awayTeam', {}).get('name', 'Away Team'),
                            'league': COMPETITION_MAP.get(comp, comp),
                            'league_code': comp,
                            'kickoff_time': m.get('utcDate', 'Upcoming'),
                            'status': m.get('status', 'SCHEDULED'),
                            'is_demo': False,
                            'feed_source': 'football-data.org (Live)',
                            'odds': None # No odds loaded by default
                        })

        if not all_fixtures:
            # Fallback real schedule template labeled DEMO
            all_fixtures = self._get_demo_upcoming_fixtures()
            return all_fixtures, True

        return all_fixtures, False

    def fetch_finished_results(self, competitions: Optional[List[str]] = None) -> Tuple[Dict[str, Dict[str, Any]], bool]:
        """
        Fetches finished / postponed / cancelled matches for auto-settlement.
        Returns: (dict_of_results_by_match_id, is_demo)
        """
        comps = competitions or ['PL', 'PD', 'SA', 'BL1', 'FL1']
        results = {}
        is_live = False

        if self.api_key:
            for comp in comps:
                data = self._get(f"competitions/{comp}/matches", {'status': 'FINISHED,POSTPONED,CANCELLED'})
                if data and 'matches' in data:
                    is_live = True
                    for m in data['matches']:
                        m_id = f"fd_{m['id']}"
                        status = m.get('status')
                        score = m.get('score', {}).get('fullTime', {})
                        h_score = score.get('home')
                        a_score = score.get('away')
                        
                        ftr = None
                        if status == 'FINISHED' and h_score is not None and a_score is not None:
                            if h_score > a_score:
                                ftr = 'H'
                            elif a_score > h_score:
                                ftr = 'A'
                            else:
                                ftr = 'D'

                        results[m_id] = {
                            'match_id': m_id,
                            'fixture_id': m['id'],
                            'home_team': m.get('homeTeam', {}).get('name'),
                            'away_team': m.get('awayTeam', {}).get('name'),
                            'status': status, # 'FINISHED', 'POSTPONED', 'CANCELLED'
                            'home_score': h_score,
                            'away_score': a_score,
                            'ftr': ftr,
                            'is_demo': False
                        }

        if not results:
            # If no live results returned, return demo results dictionary
            return self._get_demo_finished_results(), True

        return results, False

    def _get_demo_upcoming_fixtures(self) -> List[Dict[str, Any]]:
        """Fallback real-team fixtures explicitly labeled DEMO."""
        sample_slate = [
            ("fd_demo_101", "Arsenal", "Chelsea", "Premier League", "PL", "Saturday 16:00", [1.85, 3.75, 4.20]),
            ("fd_demo_102", "Manchester City", "Liverpool", "Premier League", "PL", "Sunday 17:30", [2.05, 3.60, 3.50]),
            ("fd_demo_103", "Real Madrid", "Barcelona", "La Liga", "PD", "Sunday 20:00", [2.15, 3.70, 3.20]),
            ("fd_demo_104", "Bayern Munich", "Borussia Dortmund", "Bundesliga", "BL1", "Saturday 17:30", [1.45, 5.00, 6.50]),
            ("fd_demo_105", "Inter Milan", "Juventus", "Serie A", "SA", "Sunday 19:45", [1.95, 3.40, 4.10]),
            ("fd_demo_106", "Paris SG", "Marseille", "Ligue 1", "FL1", "Sunday 20:45", [1.40, 5.25, 7.50]),
            ("fd_demo_107", "Aston Villa", "Newcastle", "Premier League", "PL", "Saturday 13:30", None),
            ("fd_demo_108", "Atletico Madrid", "Sevilla", "La Liga", "PD", "Saturday 21:00", None)
        ]
        items = []
        for mid, h, a, l, code, k, odds in sample_slate:
            items.append({
                'match_id': mid,
                'fixture_id': mid.replace('fd_demo_', ''),
                'home_team': h,
                'away_team': a,
                'league': l,
                'league_code': code,
                'kickoff_time': k,
                'status': 'SCHEDULED',
                'is_demo': True,
                'feed_source': 'DEMO / Historical Sample',
                'odds': odds
            })
        return items

    def _get_demo_finished_results(self) -> Dict[str, Dict[str, Any]]:
        """Fallback real-team finished outcomes explicitly labeled DEMO for testing."""
        return {
            "fd_demo_101": {
                'match_id': "fd_demo_101",
                'fixture_id': "101",
                'home_team': "Arsenal",
                'away_team': "Chelsea",
                'status': "FINISHED",
                'home_score': 2,
                'away_score': 1,
                'ftr': "H",
                'is_demo': True
            },
            "fd_demo_102": {
                'match_id': "fd_demo_102",
                'fixture_id': "102",
                'home_team': "Manchester City",
                'away_team': "Liverpool",
                'status': "FINISHED",
                'home_score': 1,
                'away_score': 1,
                'ftr': "D",
                'is_demo': True
            },
            "fd_demo_103": {
                'match_id': "fd_demo_103",
                'fixture_id': "103",
                'home_team': "Real Madrid",
                'away_team': "Barcelona",
                'status': "FINISHED",
                'home_score': 1,
                'away_score': 2,
                'ftr': "A",
                'is_demo': True
            },
            "fd_demo_104": {
                'match_id': "fd_demo_104",
                'fixture_id': "104",
                'home_team': "Bayern Munich",
                'away_team': "Borussia Dortmund",
                'status': "POSTPONED",
                'home_score': None,
                'away_score': None,
                'ftr': None,
                'is_demo': True
            }
        }

