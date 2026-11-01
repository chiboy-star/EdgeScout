"""
Historical Data Fetcher & Ingestion Pipeline for EdgeScout.
Ingests match results and opening/closing odds from football-data.co.uk
and European datasets for EPL, La Liga, Serie A, Bundesliga, Ligue 1,
and Champions League.
Always saves raw files to disk and supports offline cached execution.
"""
import requests
import io
import re
from pathlib import Path
from typing import List, Optional, Dict
import pandas as pd
from datetime import datetime

from edgescout.config import (
    RAW_DATA_DIR, 
    LEAGUE_CODES, 
    LEAGUE_NAMES, 
    DEFAULT_SEASONS
)


class DataFetcher:
    def __init__(self, raw_dir: Path = RAW_DATA_DIR):
        self.raw_dir = Path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) EdgeScout/1.0"
        }

    def _get_fd_url(self, season: str, league_code: str) -> str:
        """football-data.co.uk URL format: https://www.football-data.co.uk/mmz4281/2324/E0.csv"""
        return f"https://www.football-data.co.uk/mmz4281/{season}/{league_code}.csv"

    def fetch_league_season(
        self, 
        league_code: str, 
        season: str, 
        force_refresh: bool = False
    ) -> pd.DataFrame:
        """
        Fetch a single league season CSV from football-data.co.uk with local raw file caching.
        """
        raw_file = self.raw_dir / f"{season}_{league_code}.csv"
        
        # Check local cache first
        if raw_file.exists() and not force_refresh:
            try:
                df = pd.read_csv(raw_file, encoding='latin1')
                if len(df) > 0 and 'HomeTeam' in df.columns:
                    return self._clean_dataframe(df, league_code, season)
            except Exception:
                pass # Re-download if corrupted

        url = self._get_fd_url(season, league_code)
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            if resp.status_code == 200 and len(resp.content) > 100:
                # Save raw response to disk
                with open(raw_file, "wb") as f:
                    f.write(resp.content)
                df = pd.read_csv(io.StringIO(resp.text), encoding='latin1')
                return self._clean_dataframe(df, league_code, season)
            else:
                print(f"Warning: Could not fetch {url} (HTTP {resp.status_code})")
        except Exception as e:
            print(f"Error fetching {url}: {e}")

        # If download failed, check if raw_file exists anyway
        if raw_file.exists():
            df = pd.read_csv(raw_file, encoding='latin1')
            return self._clean_dataframe(df, league_code, season)

        return pd.DataFrame()

    def fetch_champions_league(self, season: str) -> pd.DataFrame:
        """
        Champions League historical records without verified market odds are dropped.
        No synthetic or neutral baseline odds are permitted.
        """
        raw_file = self.raw_dir / f"{season}_CL.csv"
        if raw_file.exists():
            try:
                df = pd.read_csv(raw_file, encoding='latin1')
                if not df.empty and 'HomeTeam' in df.columns:
                    # Require real odds columns to exist
                    if 'B365H' in df.columns and 'PSCH' in df.columns:
                        return self._clean_dataframe(df, "CL", season)
            except Exception:
                pass
        return pd.DataFrame()

    def _parse_dates(self, date_series: pd.Series) -> pd.Series:
        """Parses mixed football-data.co.uk dates (DD/MM/YYYY, DD/MM/YY, YYYY-MM-DD)."""
        clean_dates = []
        for val in date_series:
            if pd.isna(val):
                clean_dates.append(None)
                continue
            val_str = str(val).strip()
            parsed = None
            for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    parsed = datetime.strptime(val_str, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
            if parsed is None:
                # Fallback to pandas parser
                try:
                    dt = pd.to_datetime(val_str, dayfirst=True)
                    parsed = dt.strftime("%Y-%m-%d")
                except Exception:
                    parsed = None
            clean_dates.append(parsed)
        return pd.Series(clean_dates)

    def _clean_dataframe(self, df: pd.DataFrame, league_code: str, season: str) -> pd.DataFrame:
        """
        Standardizes columns, cleans team names, parses dates, and formats odds.
        """
        df = df.copy()
        # Drop empty rows
        df = df.dropna(how='all')
        if 'HomeTeam' not in df.columns or 'AwayTeam' not in df.columns:
            return pd.DataFrame()

        df = df[df['HomeTeam'].notna() & df['AwayTeam'].notna()]
        
        # Standardize team names
        df['HomeTeam'] = df['HomeTeam'].astype(str).str.strip()
        df['AwayTeam'] = df['AwayTeam'].astype(str).str.strip()
        
        # Parse Dates
        df['match_date'] = self._parse_dates(df['Date'])
        df = df[df['match_date'].notna()]
        
        df['match_time'] = df['Time'].astype(str).str.strip() if 'Time' in df.columns else ""
        
        # Result columns
        df['fthg'] = pd.to_numeric(df['FTHG'], errors='coerce')
        df['ftag'] = pd.to_numeric(df['FTAG'], errors='coerce')
        df['ftr'] = df['FTR'].astype(str).str.strip()
        df = df[df['ftr'].isin(['H', 'D', 'A'])]

        df['hthg'] = pd.to_numeric(df['HTHG'], errors='coerce') if 'HTHG' in df.columns else None
        df['htag'] = pd.to_numeric(df['HTAG'], errors='coerce') if 'HTAG' in df.columns else None
        df['htr'] = df['HTR'].astype(str).str.strip() if 'HTR' in df.columns else None

        # Build unique match_id
        df['match_id'] = df.apply(
            lambda r: f"{league_code}_{season}_{r['match_date']}_{re.sub(r'[^a-zA-Z0-9]', '', r['HomeTeam'])}_{re.sub(r'[^a-zA-Z0-9]', '', r['AwayTeam'])}",
            axis=1
        )

        df['league_code'] = league_code
        df['league_name'] = LEAGUE_NAMES.get(league_code, league_code)
        df['season'] = season
        df['home_team'] = df['HomeTeam']
        df['away_team'] = df['AwayTeam']

        # Map Odds columns safely
        def get_col(col_name: str) -> pd.Series:
            if col_name in df.columns:
                return pd.to_numeric(df[col_name], errors='coerce')
            return pd.Series(None, index=df.index, dtype=float)

        # Standard / Reference Odds
        df['b365_h'] = get_col('B365H')
        df['b365_d'] = get_col('B365D')
        df['b365_a'] = get_col('B365A')
        df['ps_h'] = get_col('PSH')
        df['ps_d'] = get_col('PSD')
        df['ps_a'] = get_col('PSA')
        df['avg_h'] = get_col('AvgH')
        df['avg_d'] = get_col('AvgD')
        df['avg_a'] = get_col('AvgA')
        df['max_h'] = get_col('MaxH')
        df['max_d'] = get_col('MaxD')
        df['max_a'] = get_col('MaxA')

        # Closing Odds
        df['b365_ch'] = get_col('B365CH')
        df['b365_cd'] = get_col('B365CD')
        df['b365_ca'] = get_col('B365CA')
        df['ps_ch'] = get_col('PSCH')
        df['ps_cd'] = get_col('PSCD')
        df['ps_ca'] = get_col('PSCA')
        df['avg_ch'] = get_col('AvgCH')
        df['avg_cd'] = get_col('AvgCD')
        df['avg_ca'] = get_col('AvgCA')
        df['max_ch'] = get_col('MaxCH')
        df['max_cd'] = get_col('MaxCD')
        df['max_ca'] = get_col('MaxCA')

        # Strictly keep real closing odds; never fill with opening odds

        cols_to_keep = [
            'match_id', 'league_code', 'league_name', 'season', 'match_date', 'match_time',
            'home_team', 'away_team', 'fthg', 'ftag', 'ftr', 'hthg', 'htag', 'htr',
            'b365_h', 'b365_d', 'b365_a', 'ps_h', 'ps_d', 'ps_a',
            'avg_h', 'avg_d', 'avg_a', 'max_h', 'max_d', 'max_a',
            'b365_ch', 'b365_cd', 'b365_ca', 'ps_ch', 'ps_cd', 'ps_ca',
            'avg_ch', 'avg_cd', 'avg_ca', 'max_ch', 'max_cd', 'max_ca'
        ]
        return df[cols_to_keep].sort_values(['match_date', 'match_time']).reset_index(drop=True)

    def fetch_all_historical_data(
        self, 
        leagues: Optional[List[str]] = None, 
        seasons: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Fetches and compiles all requested leagues and seasons into a single dataset.
        """
        target_leagues = leagues or ["E0", "SP1", "I1", "D1", "F1"]
        target_seasons = seasons or DEFAULT_SEASONS
        
        all_dfs = []
        for season in target_seasons:
            for l_code in target_leagues:
                if l_code == "CL":
                    df = self.fetch_champions_league(season)
                else:
                    df = self.fetch_league_season(l_code, season)
                if not df.empty:
                    print(f"Loaded {len(df)} matches for {l_code} ({season})")
                    all_dfs.append(df)

        if not all_dfs:
            return pd.DataFrame()

        master_df = pd.concat(all_dfs, ignore_index=True)
        # Drop duplicates by match_id
        master_df = master_df.drop_duplicates(subset=['match_id']).sort_values('match_date').reset_index(drop=True)
        return master_df
