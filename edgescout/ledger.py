"""
Paper Trading Ledger & Bankroll Engine for EdgeScout.
Implements:
- Virtual bankroll tracking
- Idempotency keys to guarantee double-tap protection
- Optimistic updates & settlement logic from REAL match results (stable IDs)
- Postponed / cancelled / void game handling with 100% stake refund
- Manual settlement override ('WON', 'LOST', 'VOID') with closing odds CLV recording
- Flat 1% default stake with fractional Kelly fallback (capped at 2% bet / 6% daily)
- Performance stats: Hit rate, ROI, Max Drawdown, Bankroll curve, Average CLV
- Strict sample size warning (< 300 settled bets)
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
        id TEXT PRIMARY KEY,               -- UUID
        idempotency_key TEXT UNIQUE NOT NULL,
        match_id TEXT NOT NULL,           -- Stable Match ID (e.g. fd_12345)
        match_name TEXT NOT NULL,
        league_code TEXT NOT NULL,
        selection TEXT NOT NULL,          -- 'H', 'D', 'A'
        odds_taken REAL NOT NULL,
        closing_odds REAL,
        clv REAL,                         -- (odds_taken / closing_odds) - 1.0
        stake REAL NOT NULL,
        stake_fraction REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN', -- 'OPEN', 'WON', 'LOST', 'VOID', 'UNDONE'
        settlement_type TEXT,             -- 'AUTO_API', 'MANUAL'
        profit_loss REAL DEFAULT 0.0,
        placed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        settled_at TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_paper_bets_status ON paper_bets(status);
    CREATE INDEX IF NOT EXISTS idx_paper_bets_idemp ON paper_bets(idempotency_key);
    CREATE INDEX IF NOT EXISTS idx_paper_bets_match_id ON paper_bets(match_id);
    """)

    # Schema migration checks if columns are missing
    cursor.execute("PRAGMA table_info(paper_bets);")
    columns = [row[1] for row in cursor.fetchall()]
    if 'clv' not in columns:
        cursor.execute("ALTER TABLE paper_bets ADD COLUMN clv REAL;")
    if 'settlement_type' not in columns:
        cursor.execute("ALTER TABLE paper_bets ADD COLUMN settlement_type TEXT;")

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
            raw_f, capped_f, _ = calculate_stake(user_prob, odds, bk, kelly_mult=0.25, max_bet_fraction=0.02)
            method = "Quarter-Kelly (User Estimate)"
            final_fraction = min(capped_f, remaining_daily_cap)
        else:
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
        If idempotency_key already exists, returns existing bet without duplicating.
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
            'match_id': match_id,
            'stake': stake,
            'odds_taken': odds,
            'new_bankroll': new_bankroll
        }

    def undo_bet(self, bet_id: str) -> Dict[str, Any]:
        """
        Rolls back an open bet (6-second undo window).
        Refunds stake immediately.
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
        actual_result: str, # 'H', 'D', 'A'
        closing_odds: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Settles a bet against match outcome ('H', 'D', 'A') or direct status.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT selection FROM paper_bets WHERE id = ?;", (bet_id,))
            row = cursor.fetchone()
            if not row:
                return {'error': 'Bet not found'}
            selection = row['selection']

        won = (actual_result == selection)
        outcome = 'WON' if won else 'LOST'
        return self.manual_settle_bet(bet_id, outcome, closing_odds)

    def manual_settle_bet(
        self,
        bet_id: str,
        outcome: str, # 'WON', 'LOST', 'VOID'
        closing_odds: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Manual settlement override (W/L/Void) for leagues not covered by free API.
        - WON: Pays out stake * odds_taken. Profit = (stake * odds_taken) - stake.
        - LOST: Loss = -stake. (Stake was already deducted at placement).
        - VOID: Match cancelled / postponed. 100% of stake is refunded to bankroll. Profit = 0.
        Calculates CLV if closing_odds is provided.
        """
        outcome = outcome.upper()
        if outcome not in ('WON', 'LOST', 'VOID'):
            return {'error': f"Invalid outcome '{outcome}'. Must be WON, LOST, or VOID."}

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM paper_bets WHERE id = ?;", (bet_id,))
            bet = cursor.fetchone()
            if not bet:
                return {'error': 'Bet not found'}
            if bet['status'] != 'OPEN':
                return {'error': f"Bet already in status {bet['status']}"}

            odds_taken = float(bet['odds_taken'])
            stake = float(bet['stake'])

            clv = None
            if closing_odds is not None and closing_odds > 0:
                clv = round((odds_taken / float(closing_odds)) - 1.0, 4)

            if outcome == 'WON':
                payout = stake * odds_taken
                pl = payout - stake
                cursor.execute("UPDATE paper_bankroll SET current_bankroll = current_bankroll + ? WHERE id = 1;", (payout,))
            elif outcome == 'LOST':
                payout = 0.0
                pl = -stake
            else: # VOID
                payout = stake
                pl = 0.0
                # Full stake refund on void
                cursor.execute("UPDATE paper_bankroll SET current_bankroll = current_bankroll + ? WHERE id = 1;", (stake,))

            cursor.execute("""
            UPDATE paper_bets SET
                status = ?,
                profit_loss = ?,
                closing_odds = ?,
                clv = ?,
                settlement_type = 'MANUAL',
                settled_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """, (outcome, pl, closing_odds, clv, bet_id))
            conn.commit()

        return {
            'bet_id': bet_id,
            'status': outcome,
            'profit_loss': pl,
            'payout': payout,
            'closing_odds': closing_odds,
            'clv': clv
        }

    def auto_settle_from_results(
        self, 
        results_by_match_id: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Auto-settles open paper bets by matching stable match IDs from football-data.org feed.
        Handles FINISHED, POSTPONED, and CANCELLED (VOID) matches.
        """
        settled_count = 0
        void_count = 0
        details = []

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM paper_bets WHERE status = 'OPEN';")
            open_bets = [dict(r) for r in cursor.fetchall()]

            for bet in open_bets:
                m_id = bet['match_id']
                if m_id not in results_by_match_id:
                    continue

                res = results_by_match_id[m_id]
                match_status = str(res.get('status', '')).upper()
                closing_odds = res.get('closing_odds')
                odds_taken = float(bet['odds_taken'])
                stake = float(bet['stake'])

                clv = None
                if closing_odds is not None and closing_odds > 0:
                    clv = round((odds_taken / float(closing_odds)) - 1.0, 4)

                if match_status == 'FINISHED':
                    ftr = res.get('ftr') # 'H', 'D', 'A'
                    if not ftr:
                        continue

                    won = (bet['selection'] == ftr)
                    if won:
                        new_status = 'WON'
                        payout = stake * odds_taken
                        pl = payout - stake
                        cursor.execute("UPDATE paper_bankroll SET current_bankroll = current_bankroll + ? WHERE id = 1;", (payout,))
                    else:
                        new_status = 'LOST'
                        payout = 0.0
                        pl = -stake

                    cursor.execute("""
                    UPDATE paper_bets SET
                        status = ?,
                        profit_loss = ?,
                        closing_odds = ?,
                        clv = ?,
                        settlement_type = 'AUTO_API',
                        settled_at = CURRENT_TIMESTAMP
                    WHERE id = ?;
                    """, (new_status, pl, closing_odds, clv, bet['id']))
                    settled_count += 1
                    details.append({
                        'bet_id': bet['id'],
                        'match_name': bet['match_name'],
                        'status': new_status,
                        'profit_loss': pl,
                        'clv': clv
                    })

                elif match_status in ('POSTPONED', 'CANCELLED', 'VOID'):
                    # Refund stake
                    cursor.execute("UPDATE paper_bankroll SET current_bankroll = current_bankroll + ? WHERE id = 1;", (stake,))
                    cursor.execute("""
                    UPDATE paper_bets SET
                        status = 'VOID',
                        profit_loss = 0.0,
                        closing_odds = ?,
                        clv = 0.0,
                        settlement_type = 'AUTO_API',
                        settled_at = CURRENT_TIMESTAMP
                    WHERE id = ?;
                    """, (closing_odds, bet['id']))
                    void_count += 1
                    details.append({
                        'bet_id': bet['id'],
                        'match_name': bet['match_name'],
                        'status': 'VOID',
                        'profit_loss': 0.0,
                        'refund': stake
                    })

            conn.commit()

        return {
            'settled_count': settled_count,
            'void_count': void_count,
            'total_processed': settled_count + void_count,
            'details': details
        }

    def get_ledger_summary(self) -> Dict[str, Any]:
        """
        Computes hit rate, ROI, P/L, bankroll curve, max drawdown, CLV metrics,
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
            WHERE status IN ('WON', 'LOST', 'VOID', 'OPEN')
            ORDER BY placed_at ASC;
            """)
            all_bets = [dict(r) for r in cursor.fetchall()]

        settled = [b for b in all_bets if b['status'] in ('WON', 'LOST', 'VOID')]
        effective_settled = [b for b in settled if b['status'] in ('WON', 'LOST')]
        n_settled = len(effective_settled)

        # Bankroll curve
        running_bk = initial_bk
        curve = [{'date': 'Initial', 'bankroll': initial_bk}]
        peak = initial_bk
        max_dd = 0.0

        total_staked = 0.0
        total_pl = 0.0
        won_count = 0
        clv_values = []

        for b in settled:
            if b['status'] in ('WON', 'LOST'):
                total_staked += float(b['stake'])
                pl = float(b['profit_loss'])
                total_pl += pl
                if b['status'] == 'WON':
                    won_count += 1
            
            if b.get('clv') is not None:
                clv_values.append(float(b['clv']))

            # Track bankroll progression
            running_bk += float(b['profit_loss'])
            if running_bk > peak:
                peak = running_bk
            dd = (peak - running_bk) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

            curve.append({
                'id': b['id'],
                'date': b['settled_at'] or b['placed_at'],
                'bankroll': round(running_bk, 2),
                'match': b['match_name'],
                'status': b['status']
            })

        roi_pct = (total_pl / total_staked * 100.0) if total_staked > 0 else 0.0
        hit_rate_pct = (won_count / n_settled * 100.0) if n_settled > 0 else 0.0
        avg_clv_pct = (sum(clv_values) / len(clv_values) * 100.0) if clv_values else 0.0

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
            'avg_clv_pct': round(avg_clv_pct, 2),
            'clv_tracked_bets': len(clv_values),
            'total_settled_bets': n_settled,
            'total_void_bets': len([b for b in settled if b['status'] == 'VOID']),
            'total_open_bets': len([b for b in all_bets if b['status'] == 'OPEN']),
            'sample_warning': sample_warning,
            'bankroll_curve': curve,
            'recent_bets': all_bets[-50:]
        }
