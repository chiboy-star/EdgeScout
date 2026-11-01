"""
Paper Trading Ledger & Bankroll Engine for EdgeScout.
Implements:
- Virtual bankroll tracking
- Idempotency keys to guarantee double-tap protection
- Optimistic updates & settlement logic
- Flat 1% default stake with fractional Kelly fallback (capped at 2% bet / 6% daily)
- Performance stats: Hit rate, ROI, Max Drawdown, Bankroll curve
- Small sample warning (< 300 settled bets)
"""
import sqlite3
import json
import uuid
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime

from edgescout.config import DEFAULT_DB_PATH
from edgescout.models.kelly import calculate_stake, kelly_fraction


def init_ledger_tables(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS paper_bankroll (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        initial_bankroll REAL NOT NULL,
        current_bankroll REAL NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS paper_bets (
        id TEXT PRIMARY KEY,               -- UUID or custom ID
        idempotency_key TEXT UNIQUE NOT NULL,
        match_id TEXT NOT NULL,
        match_name TEXT NOT NULL,
        league_code TEXT NOT NULL,
        selection TEXT NOT NULL,          -- 'H', 'D', 'A'
        odds_taken REAL NOT NULL,
        closing_odds REAL,
        stake REAL NOT NULL,
        stake_fraction REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN', -- 'OPEN', 'WON', 'LOST', 'VOID', 'UNDONE'
        profit_loss REAL DEFAULT 0.0,
        placed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        settled_at TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_paper_bets_status ON paper_bets(status);
    CREATE INDEX IF NOT EXISTS idx_paper_bets_idemp ON paper_bets(idempotency_key);
    """)
    # Initialize bankroll if empty
    cursor.execute("SELECT COUNT(*) FROM paper_bankroll WHERE id = 1;")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO paper_bankroll (id, initial_bankroll, current_bankroll) VALUES (1, 100000.0, 100000.0);")
    conn.commit()


class PaperLedger:
    def __init__(self, db_path: str = str(DEFAULT_DB_PATH)):
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            init_ledger_tables(conn)

    def get_bankroll(self) -> Dict[str, float]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT initial_bankroll, current_bankroll FROM paper_bankroll WHERE id = 1;").fetchone()
            return {
                'initial_bankroll': float(row['initial_bankroll']),
                'current_bankroll': float(row['current_bankroll'])
            }

    def reset_bankroll(self, amount: float = 100000.0):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE paper_bankroll SET initial_bankroll = ?, current_bankroll = ? WHERE id = 1;", (amount, amount))
            conn.execute("DELETE FROM paper_bets;")
            conn.commit()

    def get_daily_exposure_fraction(self) -> float:
        """Computes total bankroll fraction currently committed to open bets."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT SUM(stake_fraction) FROM paper_bets WHERE status = 'OPEN';").fetchone()
            return float(row[0]) if row[0] is not None else 0.0

    def calculate_suggested_stake(
        self, 
        odds: float, 
        user_prob: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Sizing rules:
        - Flat 1% of bankroll default.
        - Fractional Kelly only if user enters their own estimated probability.
        - Capped strictly at 2% single bet and 6% daily exposure.
        """
        bk = self.get_bankroll()['current_bankroll']
        open_exposure = self.get_daily_exposure_fraction()
        remaining_daily_cap = max(0.0, 0.06 - open_exposure)

        if user_prob is not None and 0.0 < user_prob < 1.0:
            # Quarter-Kelly based on user's own probability
            raw_f, capped_f, _ = calculate_stake(user_prob, odds, bk, kelly_mult=0.25, max_bet_fraction=0.02)
            method = "Quarter-Kelly (User Estimate)"
            final_fraction = min(capped_f, remaining_daily_cap)
        else:
            # Default flat 1% of bankroll
            method = "Flat 1% Default (Disciplined Sizing)"
            final_fraction = min(0.01, remaining_daily_cap)

        stake = round(final_fraction * bk, 2)
        return {
            'method': method,
            'suggested_fraction': round(final_fraction, 4),
            'suggested_stake': stake,
            'current_bankroll': bk,
            'daily_exposure_remaining': round(remaining_daily_cap, 4),
            'cap_enforced': final_fraction < (0.01 if user_prob is None else 0.02)
        }

    def place_bet(
        self,
        idempotency_key: str,
        match_id: str,
        match_name: str,
        league_code: str,
        selection: str,
        odds: float,
        stake: float,
        stake_fraction: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Places a paper bet with idempotency check.
        If idempotency_key already exists, returns existing bet without duplicating!
        """
        bet_id = str(uuid.uuid4())
        bk = self.get_bankroll()['current_bankroll']

        if stake_fraction is None:
            stake_fraction = stake / bk if bk > 0 else 0.01

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Check idempotency
            cursor.execute("SELECT * FROM paper_bets WHERE idempotency_key = ?;", (idempotency_key,))
            existing = cursor.fetchone()
            if existing:
                return {
                    'status': 'ALREADY_EXISTS',
                    'bet': dict(existing),
                    'message': 'Idempotent request: bet already placed.'
                }

            # Enforce bankroll subtraction
            new_bankroll = bk - stake
            cursor.execute("UPDATE paper_bankroll SET current_bankroll = ? WHERE id = 1;", (new_bankroll,))

            cursor.execute("""
            INSERT INTO paper_bets (
                id, idempotency_key, match_id, match_name, league_code,
                selection, odds_taken, stake, stake_fraction, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN');
            """, (
                bet_id, idempotency_key, match_id, match_name, league_code,
                selection, float(odds), float(stake), float(stake_fraction)
            ))
            conn.commit()

        return {
            'status': 'PLACED',
            'bet_id': bet_id,
            'idempotency_key': idempotency_key,
            'stake': stake,
            'odds': odds,
            'new_bankroll': new_bankroll
        }

    def undo_bet(self, bet_id: str) -> Dict[str, Any]:
        """
        Rolls back an open bet (6-second undo window).
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM paper_bets WHERE id = ?;", (bet_id,))
            bet = cursor.fetchone()
            if not bet:
                return {'error': 'Bet not found'}
            if bet['status'] != 'OPEN':
                return {'error': 'Cannot undo already settled bet'}

            # Refund stake to bankroll
            refund = float(bet['stake'])
            cursor.execute("UPDATE paper_bankroll SET current_bankroll = current_bankroll + ? WHERE id = 1;", (refund,))
            cursor.execute("UPDATE paper_bets SET status = 'UNDONE' WHERE id = ?;", (bet_id,))
            conn.commit()

        return {'status': 'UNDONE', 'refund': refund}

    def settle_bet(
        self, 
        bet_id: str, 
        actual_result: str, 
        closing_odds: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Settles a paper bet against match outcome ('H', 'D', 'A').
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM paper_bets WHERE id = ?;", (bet_id,))
            bet = cursor.fetchone()
            if not bet:
                return {'error': 'Bet not found'}
            if bet['status'] not in ('OPEN',):
                return {'error': f"Bet already in status {bet['status']}"}

            selection = bet['selection']
            odds = float(bet['odds_taken'])
            stake = float(bet['stake'])
            won = (actual_result == selection)

            if won:
                payout = stake * odds
                pl = payout - stake
                new_status = 'WON'
            else:
                payout = 0.0
                pl = -stake
                new_status = 'LOST'

            # Update bankroll with return
            cursor.execute("UPDATE paper_bankroll SET current_bankroll = current_bankroll + ? WHERE id = 1;", (payout,))

            # Update bet record
            cursor.execute("""
            UPDATE paper_bets SET
                status = ?,
                profit_loss = ?,
                closing_odds = ?,
                settled_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """, (new_status, pl, closing_odds, bet_id))
            conn.commit()

        return {
            'bet_id': bet_id,
            'status': new_status,
            'profit_loss': pl,
            'payout': payout
        }

    def get_ledger_summary(self) -> Dict[str, Any]:
        """
        Computes hit rate, ROI, P/L, bankroll curve, max drawdown,
        and enforces the 300-settled-bet sample size warning.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            bk = conn.execute("SELECT initial_bankroll, current_bankroll FROM paper_bankroll WHERE id = 1;").fetchone()
            initial_bk = float(bk['initial_bankroll'])
            current_bk = float(bk['current_bankroll'])

            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM paper_bets 
            WHERE status IN ('WON', 'LOST', 'OPEN')
            ORDER BY placed_at ASC;
            """)
            all_bets = [dict(r) for r in cursor.fetchall()]

        settled = [b for b in all_bets if b['status'] in ('WON', 'LOST')]
        n_settled = len(settled)

        # Bankroll curve
        running_bk = initial_bk
        curve = [{'date': 'Initial', 'bankroll': initial_bk}]
        peak = initial_bk
        max_dd = 0.0

        total_staked = 0.0
        total_pl = 0.0
        won_count = 0

        for b in settled:
            total_staked += float(b['stake'])
            pl = float(b['profit_loss'])
            total_pl += pl
            running_bk += (pl + float(b['stake'])) - float(b['stake']) # net change
            if b['status'] == 'WON':
                won_count += 1
            
            if running_bk > peak:
                peak = running_bk
            dd = (peak - running_bk) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

            curve.append({
                'id': b['id'],
                'date': b['settled_at'] or b['placed_at'],
                'bankroll': round(running_bk, 2),
                'match': b['match_name']
            })

        roi_pct = (total_pl / total_staked * 100.0) if total_staked > 0 else 0.0
        hit_rate_pct = (won_count / n_settled * 100.0) if n_settled > 0 else 0.0

        # Sample size warning (< 300 bets)
        sample_warning = {
            'has_warning': n_settled < 300,
            'settled_count': n_settled,
            'target_count': 300,
            'progress_pct': round((n_settled / 300.0) * 100.0, 1),
            'message': f"Sample size too small to judge statistically ({n_settled} of 300 settled bets). Bookmaker margin dominates short-term variance."
        }

        return {
            'initial_bankroll': initial_bk,
            'current_bankroll': current_bk,
            'net_profit_loss': round(total_pl, 2),
            'roi_pct': round(roi_pct, 2),
            'hit_rate_pct': round(hit_rate_pct, 2),
            'max_drawdown_pct': round(max_dd * 100.0, 2),
            'total_settled_bets': n_settled,
            'total_open_bets': len([b for b in all_bets if b['status'] == 'OPEN']),
            'sample_warning': sample_warning,
            'bankroll_curve': curve,
            'recent_bets': all_bets[-50:]
        }

