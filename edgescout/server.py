"""
Minimal, dependency-free local HTTP server for EdgeScout.
Runs on Python standard library (http.server) with zero external dependencies.
Provides REST JSON endpoints for:
- /api/fixtures (Today & This Week)
- /api/bets (Paper Ledger)
- /api/settle/auto (Real football-data.org settlement)
- /api/settle/manual (Manual override W/L/Void with closing odds CLV)
- /api/accumulator (Audited accumulator compounding overround)
- /api/strategy (13-season tester with Design vs Holdout split & trial logging)
"""
import http.server
import socketserver
import json
import urllib.parse
from pathlib import Path
from typing import Dict, Any, Optional

from edgescout.config import DEFAULT_DB_PATH, BASE_DIR
from edgescout.ledger import PaperLedger
from edgescout.fixtures import get_market_fixtures, analyze_fixture_market
from edgescout.data.football_data_org import FootballDataOrgClient
from edgescout.accumulator import calculate_accumulator
from edgescout.strategy_tester import StrategyRule, run_strategy_test

STATIC_DIR = BASE_DIR / "dashboard"


class EdgeScoutRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, indent=2).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def _read_body_json(self) -> Dict[str, Any]:
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            return {}
        body_bytes = self.rfile.read(content_length)
        return json.loads(body_bytes.decode('utf-8'))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/api/fixtures':
            fixtures = get_market_fixtures()
            self._send_json({'fixtures': fixtures})
            return

        elif path == '/api/bets':
            ledger = PaperLedger()
            summary = ledger.get_ledger_summary()
            self._send_json(summary)
            return

        elif path == '/api/strategy/trials':
            import sqlite3
            conn = sqlite3.connect(DEFAULT_DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM strategy_trials;")
            count = cur.fetchone()[0]
            cur.execute("""
            SELECT trial_id, executed_at, rule_description, holdout_roi, holdout_ci_low, holdout_ci_high, verdict 
            FROM strategy_trials ORDER BY trial_id DESC LIMIT 20;
            """)
            recent = [
                {
                    'id': r[0], 'time': r[1], 'rule': r[2], 
                    'holdout_roi': r[3], 'ci': (r[4], r[5]), 'verdict': r[6]
                }
                for r in cur.fetchall()
            ]
            conn.close()
            self._send_json({'total_trials': count, 'recent': recent})
            return

        # Fallback to serving static HTML
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_body_json()

        ledger = PaperLedger()

        if path == '/api/bets/place':
            res = ledger.place_bet(
                idempotency_key=body.get('idempotency_key', ''),
                match_id=body.get('match_id', ''),
                match_name=body.get('match_name', ''),
                league_code=body.get('league_code', 'CUSTOM'),
                selection=body.get('selection', 'H'),
                odds=float(body.get('odds', 1.0)),
                stake=float(body.get('stake', 1000.0))
            )
            self._send_json(res)
            return

        elif path == '/api/bets/undo':
            bet_id = body.get('bet_id', '')
            res = ledger.undo_bet(bet_id)
            self._send_json(res)
            return

        elif path == '/api/settle/manual':
            bet_id = body.get('bet_id', '')
            outcome = body.get('outcome', 'WON') # 'WON', 'LOST', 'VOID'
            closing_odds = body.get('closing_odds')
            if closing_odds is not None:
                closing_odds = float(closing_odds)
            res = ledger.manual_settle_bet(bet_id, outcome, closing_odds)
            self._send_json(res)
            return

        elif path == '/api/settle/auto':
            client = FootballDataOrgClient()
            results, is_demo = client.fetch_finished_results()
            res = ledger.auto_settle_from_results(results)
            res['is_demo_feed'] = is_demo
            self._send_json(res)
            return

        elif path == '/api/accumulator':
            legs = body.get('legs', [])
            stake = float(body.get('stake', 1000.0))
            analysis = calculate_accumulator(legs, stake=stake)
            self._send_json(analysis)
            return

        elif path == '/api/strategy/run':
            rule = StrategyRule(
                name=body.get('name', 'Custom Rule'),
                leagues=body.get('leagues'),
                min_odds=float(body.get('min_odds', 1.01)),
                max_odds=float(body.get('max_odds', 100.0)),
                selections=body.get('selections', ['H']),
                role_filter=body.get('role_filter', 'ALL')
            )
            res = run_strategy_test(rule)
            self._send_json(res)
            return

        elif path == '/api/bankroll/reset':
            ledger.reset_bankroll(100000.0)
            self._send_json({'status': 'RESET', 'bankroll': 100000.0})
            return

        self._send_json({'error': 'Not found'}, status=404)


def run_server(port: int = 8000):
    with socketserver.TCPServer(("127.0.0.1", port), EdgeScoutRequestHandler) as httpd:
        print(f"EdgeScout local server running at http://127.0.0.1:{port}/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")


if __name__ == '__main__':
    run_server()
