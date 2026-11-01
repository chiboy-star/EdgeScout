"""
Storage and SQLite Database Engine for EdgeScout.
Stores raw API responses, structured match data, historical odds,
backtest logs, and settled paper trades.
"""
import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
import pandas as pd
from edgescout.config import DEFAULT_DB_PATH, DATA_DIR


class Database:
    def __init__(self, db_path: Union[str, Path] = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript("""
            CREATE TABLE IF NOT EXISTS matches (
                match_id TEXT PRIMARY KEY,
                league_code TEXT NOT NULL,
                league_name TEXT,
                season TEXT NOT NULL,
                match_date TEXT NOT NULL,
                match_time TEXT,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                fthg INTEGER,
                ftag INTEGER,
                ftr TEXT,
                hthg INTEGER,
                htag INTEGER,
                htr TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS odds (
                match_id TEXT PRIMARY KEY,
                b365_h REAL,
                b365_d REAL,
                b365_a REAL,
                ps_h REAL,
                ps_d REAL,
                ps_a REAL,
                avg_h REAL,
                avg_d REAL,
                avg_a REAL,
                max_h REAL,
                max_d REAL,
                max_a REAL,
                -- Closing Odds
                b365_ch REAL,
                b365_cd REAL,
                b365_ca REAL,
                ps_ch REAL,
                ps_cd REAL,
                ps_ca REAL,
                avg_ch REAL,
                avg_cd REAL,
                avg_ca REAL,
                max_ch REAL,
                max_cd REAL,
                max_ca REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (match_id) REFERENCES matches(match_id)
            );

            CREATE TABLE IF NOT EXISTS raw_api_cache (
                endpoint_key TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                url TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                response_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS backtest_bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT NOT NULL,
                match_date TEXT NOT NULL,
                league TEXT NOT NULL,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                selection TEXT NOT NULL, -- 'H', 'D', 'A'
                model_prob REAL NOT NULL,
                market_prob REAL NOT NULL,
                fair_odds REAL NOT NULL,
                odds_taken REAL NOT NULL,
                closing_odds REAL,
                edge REAL NOT NULL,
                stake REAL NOT NULL,
                actual_result TEXT NOT NULL,
                won INTEGER NOT NULL,
                profit_loss REAL NOT NULL,
                clv REAL,
                threshold REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (match_id) REFERENCES matches(match_id)
            );

            CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(match_date);
            CREATE INDEX IF NOT EXISTS idx_matches_league ON matches(league_code);
            CREATE INDEX IF NOT EXISTS idx_backtest_match_date ON backtest_bets(match_date);
            """)

    def save_matches_and_odds(self, matches_df: pd.DataFrame):
        """
        Upserts matches and odds DataFrames into SQLite.
        """
        if matches_df.empty:
            return

        with self.get_connection() as conn:
            cursor = conn.cursor()
            for _, row in matches_df.iterrows():
                # Upsert match
                cursor.execute("""
                INSERT INTO matches (
                    match_id, league_code, league_name, season, match_date, match_time,
                    home_team, away_team, fthg, ftag, ftr, hthg, htag, htr
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(match_id) DO UPDATE SET
                    fthg=excluded.fthg,
                    ftag=excluded.ftag,
                    ftr=excluded.ftr;
                """, (
                    str(row['match_id']),
                    str(row['league_code']),
                    str(row.get('league_name', '')),
                    str(row['season']),
                    str(row['match_date']),
                    str(row.get('match_time', '')),
                    str(row['home_team']),
                    str(row['away_team']),
                    int(row['fthg']) if pd.notna(row.get('fthg')) else None,
                    int(row['ftag']) if pd.notna(row.get('ftag')) else None,
                    str(row['ftr']) if pd.notna(row.get('ftr')) else None,
                    int(row['hthg']) if pd.notna(row.get('hthg')) else None,
                    int(row['htag']) if pd.notna(row.get('htag')) else None,
                    str(row['htr']) if pd.notna(row.get('htr')) else None
                ))

                # Upsert odds
                cursor.execute("""
                INSERT INTO odds (
                    match_id, b365_h, b365_d, b365_a,
                    ps_h, ps_d, ps_a,
                    avg_h, avg_d, avg_a,
                    max_h, max_d, max_a,
                    b365_ch, b365_cd, b365_ca,
                    ps_ch, ps_cd, ps_ca,
                    avg_ch, avg_cd, avg_ca,
                    max_ch, max_cd, max_ca
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(match_id) DO UPDATE SET
                    b365_ch=excluded.b365_ch,
                    b365_cd=excluded.b365_cd,
                    b365_ca=excluded.b365_ca,
                    ps_ch=excluded.ps_ch,
                    ps_cd=excluded.ps_cd,
                    ps_ca=excluded.ps_ca,
                    avg_ch=excluded.avg_ch,
                    avg_cd=excluded.avg_cd,
                    avg_ca=excluded.avg_ca,
                    max_ch=excluded.max_ch,
                    max_cd=excluded.max_cd,
                    max_ca=excluded.max_ca;
                """, (
                    str(row['match_id']),
                    float(row['b365_h']) if pd.notna(row.get('b365_h')) else None,
                    float(row['b365_d']) if pd.notna(row.get('b365_d')) else None,
                    float(row['b365_a']) if pd.notna(row.get('b365_a')) else None,
                    float(row['ps_h']) if pd.notna(row.get('ps_h')) else None,
                    float(row['ps_d']) if pd.notna(row.get('ps_d')) else None,
                    float(row['ps_a']) if pd.notna(row.get('ps_a')) else None,
                    float(row['avg_h']) if pd.notna(row.get('avg_h')) else None,
                    float(row['avg_d']) if pd.notna(row.get('avg_d')) else None,
                    float(row['avg_a']) if pd.notna(row.get('avg_a')) else None,
                    float(row['max_h']) if pd.notna(row.get('max_h')) else None,
                    float(row['max_d']) if pd.notna(row.get('max_d')) else None,
                    float(row['max_a']) if pd.notna(row.get('max_a')) else None,
                    float(row['b365_ch']) if pd.notna(row.get('b365_ch')) else None,
                    float(row['b365_cd']) if pd.notna(row.get('b365_cd')) else None,
                    float(row['b365_ca']) if pd.notna(row.get('b365_ca')) else None,
                    float(row['ps_ch']) if pd.notna(row.get('ps_ch')) else None,
                    float(row['ps_cd']) if pd.notna(row.get('ps_cd')) else None,
                    float(row['ps_ca']) if pd.notna(row.get('ps_ca')) else None,
                    float(row['avg_ch']) if pd.notna(row.get('avg_ch')) else None,
                    float(row['avg_cd']) if pd.notna(row.get('avg_cd')) else None,
                    float(row['avg_ca']) if pd.notna(row.get('avg_ca')) else None,
                    float(row['max_ch']) if pd.notna(row.get('max_ch')) else None,
                    float(row['max_cd']) if pd.notna(row.get('max_cd')) else None,
                    float(row['max_ca']) if pd.notna(row.get('max_ca')) else None
                ))

    def load_clean_dataset(self, league_code: Optional[str] = None) -> pd.DataFrame:
        """
        Loads joined matches and odds into a clean DataFrame for modeling and backtesting.
        """
        query = """
        SELECT 
            m.match_id, m.league_code, m.league_name, m.season, m.match_date, m.match_time,
            m.home_team, m.away_team, m.fthg, m.ftag, m.ftr,
            o.b365_h, o.b365_d, o.b365_a,
            o.ps_h, o.ps_d, o.ps_a,
            o.avg_h, o.avg_d, o.avg_a,
            o.max_h, o.max_d, o.max_a,
            o.b365_ch, o.b365_cd, o.b365_ca,
            o.ps_ch, o.ps_cd, o.ps_ca,
            o.avg_ch, o.avg_cd, o.avg_ca,
            o.max_ch, o.max_cd, o.max_ca
        FROM matches m
        JOIN odds o ON m.match_id = o.match_id
        WHERE m.ftr IS NOT NULL
        """
        params = []
        if league_code:
            query += " AND m.league_code = ?"
            params.append(league_code)
        query += " ORDER BY m.match_date ASC, m.match_time ASC;"
        
        with self.get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)
        
        if not df.empty:
            df['match_date'] = pd.to_datetime(df['match_date'])
        return df

    def cache_api_response(self, endpoint_key: str, provider: str, url: str, status_code: int, text: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO raw_api_cache (endpoint_key, provider, url, status_code, response_text)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(endpoint_key) DO UPDATE SET
                status_code=excluded.status_code,
                response_text=excluded.response_text,
                created_at=CURRENT_TIMESTAMP;
            """, (endpoint_key, provider, url, status_code, text))

    def get_cached_api_response(self, endpoint_key: str) -> Optional[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT response_text FROM raw_api_cache WHERE endpoint_key = ?;", (endpoint_key,))
            row = cursor.fetchone()
            return row['response_text'] if row else None

