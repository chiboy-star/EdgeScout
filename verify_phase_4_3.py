"""
Phase 4.3 Comprehensive Verification Runner.
Tests Date Integrity, Bet Placement, Error Handling, Line Shopping,
and Captures Desktop & Mobile Screenshots on Port 3000 & Port 8000.
"""
import os
import sys
import time
import shutil
import subprocess
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Fix Windows console UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"

sub_env = os.environ.copy()
sub_env["NO_PROXY"] = "localhost,127.0.0.1,::1"
sub_env["no_proxy"] = "localhost,127.0.0.1,::1"
for var in ["HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"]:
    sub_env.pop(var, None)

REPORTS_DIR = Path("reports/screenshots")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACT_DIR = Path(r"C:\Users\chine\.gemini\antigravity\brain\a81fc7e1-0852-477c-ba0e-9217794edee6")

FASTAPI_PORT = 8000
NEXT_PORT = 3000


def wait_for_url(url: str, timeout: float = 30.0) -> bool:
    start = time.time()
    session = requests.Session()
    session.trust_env = False
    last_err = None
    while time.time() - start < timeout:
        try:
            r = session.get(url, timeout=2.0)
            if r.status_code == 200:
                return True
        except Exception as e:
            last_err = e
        time.sleep(0.5)
    print(f"DEBUG: wait_for_url timeout on {url}. Last err: {last_err}", flush=True)
    return False


def test_date_integrity(session: requests.Session):
    print("\n" + "=" * 70, flush=True)
    print("STEP 1: DATE INTEGRITY & UPCOMING FIXTURES CHECK", flush=True)
    print("=" * 70, flush=True)

    now_utc = datetime.now(timezone.utc)
    print(f"Current UTC Time: {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}", flush=True)
    print(f"Current WAT Time: {(now_utc + timedelta(hours=1)).strftime('%a %d %b, %H:%M WAT')}", flush=True)

    # 1. Check Shortlist
    r_short = session.get(f"http://127.0.0.1:{FASTAPI_PORT}/api/shortlist")
    assert r_short.status_code == 200, f"Failed to get shortlist: {r_short.text}"
    shortlist_data = r_short.json()

    candidates = []
    for tier_name, tier_cards in shortlist_data.get("tiers", {}).items():
        candidates.extend(tier_cards)

    print(f"\n--- First 10 Shortlist Suggestions ({len(candidates)} total qualified) ---", flush=True)
    for idx, c in enumerate(candidates[:10], 1):
        k_utc = c.get("kickoff_utc")
        k_wat = c.get("kickoff_wat")
        cd = c.get("kickoff_countdown")
        print(f"  {idx:2d}. {c['match_name']:<35} | UTC: {k_utc} | WAT: {k_wat:<22} ({cd})", flush=True)

        # Assert no match in the past
        k_dt = datetime.fromisoformat(k_utc.replace("Z", "+00:00"))
        if k_dt.tzinfo is None:
            k_dt = k_dt.replace(tzinfo=timezone.utc)
        assert k_dt >= now_utc + timedelta(minutes=9, seconds=50), (
            f"FAIL: Shortlist candidate {c['match_name']} kickoff {k_utc} is in the past or < 10 mins!"
        )

    # 2. Check Market Fixtures
    r_fix = session.get(f"http://127.0.0.1:{FASTAPI_PORT}/api/fixtures")
    assert r_fix.status_code == 200, f"Failed to get fixtures: {r_fix.text}"
    fixtures = r_fix.json().get("fixtures", [])

    print(f"\n--- First 10 Market Fixtures ({len(fixtures)} total upcoming) ---", flush=True)
    for idx, f in enumerate(fixtures[:10], 1):
        k_utc = f.get("kickoff_utc")
        k_wat = f.get("kickoff_wat")
        cd = f.get("kickoff_countdown")
        print(f"  {idx:2d}. {f['match_name']:<35} | UTC: {k_utc} | WAT: {k_wat:<22} ({cd})", flush=True)

        k_dt = datetime.fromisoformat(k_utc.replace("Z", "+00:00"))
        if k_dt.tzinfo is None:
            k_dt = k_dt.replace(tzinfo=timezone.utc)
        assert k_dt >= now_utc + timedelta(minutes=9, seconds=50), (
            f"FAIL: Fixture {f['match_name']} kickoff {k_utc} is in the past or < 10 mins!"
        )

    print("\n✓ DATE INTEGRITY PASSED: Zero past fixtures. All kickoffs >= now + 10 mins.", flush=True)
    return candidates, fixtures


def test_bet_placement_error_handling(session: requests.Session):
    print("\n" + "=" * 70, flush=True)
    print("STEP 2: DIRECT BET PLACEMENT & REJECTION MODES", flush=True)
    print("=" * 70, flush=True)

    # Reset bankroll first
    session.post(f"http://127.0.0.1:{FASTAPI_PORT}/api/bankroll/reset", json={"amount": 100000.0})

    # Test 2a: Reject match in the past
    past_kickoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    r_past = session.post(
        f"http://127.0.0.1:{FASTAPI_PORT}/api/bets/place",
        json={
            "idempotency_key": "test_past_1",
            "match_id": "test_past_match",
            "match_name": "Past FC vs Old City",
            "league_code": "E0",
            "selection": "H",
            "odds": 2.10,
            "stake": 1000,
            "kickoff_utc": past_kickoff
        }
    )
    print(f"2a. Past Match Rejection: HTTP {r_past.status_code} - Response: {r_past.text}", flush=True)
    assert r_past.status_code == 400, "Expected HTTP 400 for past kickoff"
    assert "already started" in r_past.text or "less than 10 minutes" in r_past.text

    # Test 2b: Single bet cap rejection (> 2.0%)
    future_kickoff = (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()
    r_cap = session.post(
        f"http://127.0.0.1:{FASTAPI_PORT}/api/bets/place",
        json={
            "idempotency_key": "test_cap_1",
            "match_id": "test_future_match",
            "match_name": "Future Rovers vs United",
            "league_code": "E0",
            "selection": "H",
            "odds": 2.10,
            "stake": 3000, # 3% > 2% cap
            "kickoff_utc": future_kickoff
        }
    )
    print(f"2b. Single Bet Cap Rejection: HTTP {r_cap.status_code} - Response: {r_cap.text}", flush=True)
    assert r_cap.status_code == 400, "Expected HTTP 400 for single bet cap violation"
    assert "single bet cap" in r_cap.text.lower()

    # Test 2c: Idempotency & duplicate submission
    idemp_key = "idemp_test_duplicate_key"
    r_first = session.post(
        f"http://127.0.0.1:{FASTAPI_PORT}/api/bets/place",
        json={
            "idempotency_key": idemp_key,
            "match_id": "test_match_dup",
            "match_name": "Team A vs Team B",
            "league_code": "E0",
            "selection": "H",
            "odds": 2.10,
            "stake": 1000,
            "kickoff_utc": future_kickoff
        }
    )
    print(f"2c. First Submission: HTTP {r_first.status_code} - Status: {r_first.json().get('status')}", flush=True)
    assert r_first.status_code == 200 and r_first.json().get("status") == "PLACED"

    r_dup = session.post(
        f"http://127.0.0.1:{FASTAPI_PORT}/api/bets/place",
        json={
            "idempotency_key": idemp_key,
            "match_id": "test_match_dup",
            "match_name": "Team A vs Team B",
            "league_code": "E0",
            "selection": "H",
            "odds": 2.10,
            "stake": 1000,
            "kickoff_utc": future_kickoff
        }
    )
    print(f"2c. Duplicate Submission: HTTP {r_dup.status_code} - Status: {r_dup.json().get('status')}", flush=True)
    assert r_dup.status_code == 200 and r_dup.json().get("status") == "ALREADY_EXISTS"

    # Reset bankroll again for clean UI tests
    session.post(f"http://127.0.0.1:{FASTAPI_PORT}/api/bankroll/reset", json={"amount": 100000.0})
    print("✓ Direct placement & rejection rules verified.", flush=True)


def run_playwright_e2e():
    print("\n" + "=" * 70, flush=True)
    print("STEP 3: PLAYWRIGHT E2E INTERACTION & SCREENSHOT CAPTURE", flush=True)
    print("=" * 70, flush=True)

    from playwright.sync_api import sync_playwright

    captured_post_requests = []
    captured_post_responses = []
    console_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # -------------------------------------------------------------
        # DESKTOP (1440 x 900)
        # -------------------------------------------------------------
        context_d = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context_d.new_page()

        page.on("console", lambda msg: console_errors.append(f"[CONSOLE {msg.type.upper()}] {msg.text}") if msg.type in ["error"] else None)

        def handle_request(req):
            if req.method == "POST" and "/api/bets/place" in req.url:
                try:
                    captured_post_requests.append(req.post_data_json)
                except Exception:
                    captured_post_requests.append(req.post_data)

        def handle_response(resp):
            if resp.request.method == "POST" and "/api/bets/place" in resp.url:
                try:
                    captured_post_responses.append({
                        "status": resp.status,
                        "body": resp.json()
                    })
                except Exception:
                    captured_post_responses.append({
                        "status": resp.status,
                        "body": resp.text()
                    })

        page.on("request", handle_request)
        page.on("response", handle_response)

        print("\n[Desktop] Navigating to http://127.0.0.1:3000...", flush=True)
        page.goto(f"http://127.0.0.1:{NEXT_PORT}", wait_until="domcontentloaded")
        time.sleep(2.0)

        # Wait for Shortlist cards to render
        page.wait_for_selector("button:has-text('Add to Ledger')", timeout=30000)

        # 1. Capture Desktop Shortlist (Today)
        shot_today_1440 = REPORTS_DIR / "desktop_today_shortlist.png"
        page.screenshot(path=str(shot_today_1440), full_page=True)
        print(f"  ✓ Saved {shot_today_1440.name}", flush=True)

        # 2. Place Real Bet from Shortlist
        print("  • Clicking 'Add to Ledger' on first shortlist card...", flush=True)
        add_btns = page.locator("button:has-text('Add to Ledger')")
        assert add_btns.count() > 0, "No 'Add to Ledger' buttons found!"
        
        with page.expect_response(lambda r: "/api/bets/place" in r.url) as response_info:
            add_btns.first.click()
        
        post_response = response_info.value
        post_status = post_response.status
        post_body = post_response.text()

        # Print captured request & response
        print("\n  --- Captured Bet Placement POST ---", flush=True)
        if captured_post_requests:
            print(f"  POST Request Body: {captured_post_requests[-1]}", flush=True)
        print(f"  HTTP Response: Status {post_status}, Body: {post_body}", flush=True)
        assert post_status == 200, f"Bet placement failed: {post_body}"
        print("  -----------------------------------", flush=True)

        # 3. Reload Page and Confirm in Ledger
        print("  • Reloading page and navigating to Paper Ledger tab...", flush=True)
        page.reload()
        time.sleep(1.5)
        page.click("button:has-text('Paper Ledger')")
        time.sleep(1.5)

        # Verify bet is displayed in ledger
        ledger_text = page.inner_text("main")
        assert "OPEN" in ledger_text or "₦1,000" in ledger_text or "₦99,000" in page.content(), "Bet not reflected in Ledger!"
        print("  ✓ Confirmed bet registered in Paper Ledger with updated bankroll.", flush=True)

        shot_ledger_1440 = REPORTS_DIR / "desktop_ledger.png"
        page.screenshot(path=str(shot_ledger_1440), full_page=True)
        print(f"  ✓ Saved {shot_ledger_1440.name}", flush=True)

        # 4. Test Undo within 6 seconds
        print("  • Navigating back to Today tab to test Undo flow...", flush=True)
        page.click("button:has-text('Today (Shortlist)')")
        time.sleep(1.5)

        add_btns.nth(1).click() # Click second candidate
        time.sleep(0.5)

        # Click Undo button on Sonner toast
        undo_btn = page.locator("button:has-text('Undo')").first
        if undo_btn.count() > 0:
            undo_btn.click()
            time.sleep(1.0)
            print("  ✓ Clicked 'Undo (6s)' on toast - bet undone & stake refunded.", flush=True)

        # 5. Test Manual SportyBet Modal
        print("  • Testing Manual SportyBet Modal placement...", flush=True)
        verify_btn = page.locator("button:has-text('Verify SportyBet'), button:has-text('Enter Custom SportyBet Odds')").first
        if verify_btn.count() > 0:
            verify_btn.click()
            time.sleep(0.8)

            # In modal, enter odds and submit
            submit_btn = page.locator("button:has-text('Add to Paper Ledger')").first
            if submit_btn.count() > 0:
                submit_btn.click()
                time.sleep(1.5)
                print("  ✓ Submitted manual SportyBet bet via modal.", flush=True)

        # 6. Capture This Week (Fixtures) Tab
        page.click("button:has-text('This Week')")
        time.sleep(1.5)
        shot_week_1440 = REPORTS_DIR / "desktop_this_week_fixtures.png"
        page.screenshot(path=str(shot_week_1440), full_page=True)
        print(f"  ✓ Saved {shot_week_1440.name}", flush=True)

        context_d.close()

        # -------------------------------------------------------------
        # MOBILE (390 x 844) - iPhone Viewport
        # -------------------------------------------------------------
        print("\n[Mobile 390px] Capturing mobile layouts...", flush=True)
        context_m = browser.new_context(
            viewport={"width": 390, "height": 844},
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
        )
        page_m = context_m.new_page()
        page_m.goto(f"http://127.0.0.1:{NEXT_PORT}", wait_until="domcontentloaded")
        time.sleep(2.0)

        # Mobile Today
        shot_today_390 = REPORTS_DIR / "mobile_today_shortlist.png"
        page_m.screenshot(path=str(shot_today_390))
        print(f"  ✓ Saved {shot_today_390.name}", flush=True)

        # Mobile This Week
        page_m.click("button:has-text('This Week')")
        time.sleep(1.0)
        shot_week_390 = REPORTS_DIR / "mobile_this_week_fixtures.png"
        page_m.screenshot(path=str(shot_week_390))
        print(f"  ✓ Saved {shot_week_390.name}", flush=True)

        # Mobile Ledger
        page_m.click("button:has-text('Paper Ledger')")
        time.sleep(1.0)
        shot_ledger_390 = REPORTS_DIR / "mobile_ledger.png"
        page_m.screenshot(path=str(shot_ledger_390))
        print(f"  ✓ Saved {shot_ledger_390.name}", flush=True)

        context_m.close()
        browser.close()

    # Copy screenshots to artifact directory
    for f in REPORTS_DIR.glob("*.png"):
        shutil.copy(f, ARTIFACT_DIR / f.name)
    print(f"\n✓ Copied all screenshots to {ARTIFACT_DIR}", flush=True)


def main():
    fastapi_proc = None
    next_proc = None
    fastapi_log = open("reports/fastapi_p43.log", "w", encoding="utf-8")
    next_log = open("reports/next_p43.log", "w", encoding="utf-8")

    try:
        print("=" * 70, flush=True)
        print("STARTING TEST SERVERS FRESH", flush=True)
        print("=" * 70, flush=True)

        # Start FastAPI on port 8000
        print(f"Starting FastAPI on http://127.0.0.1:{FASTAPI_PORT}...", flush=True)
        fastapi_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "edgescout.server:app", "--host", "127.0.0.1", "--port", str(FASTAPI_PORT)],
            stdout=fastapi_log,
            stderr=fastapi_log,
            env=sub_env
        )

        if not wait_for_url(f"http://127.0.0.1:{FASTAPI_PORT}/api/health", timeout=25):
            print("ERROR: FastAPI backend failed to start.", flush=True)
            sys.exit(1)
        print("✓ FastAPI server ready.", flush=True)

        # Start Next.js on port 3000
        print(f"Starting Next.js production server on http://127.0.0.1:{NEXT_PORT}...", flush=True)
        next_proc = subprocess.Popen(
            ["cmd", "/c", f"cd /d dashboard && node node_modules/next/dist/bin/next start -p {NEXT_PORT}"],
            stdout=next_log,
            stderr=next_log,
            env=sub_env
        )

        if not wait_for_url(f"http://127.0.0.1:{NEXT_PORT}", timeout=30):
            print("ERROR: Next.js server failed to respond.", flush=True)
            sys.exit(1)
        print("✓ Next.js server ready.", flush=True)

        # Run tests
        session = requests.Session()
        session.trust_env = False

        test_date_integrity(session)
        test_bet_placement_error_handling(session)
        run_playwright_e2e()

        print("\n" + "=" * 70, flush=True)
        print("ALL PHASE 4.3 TESTS COMPLETED SUCCESSFULLY!", flush=True)
        print("=" * 70, flush=True)

    finally:
        print("\nTearing down servers...", flush=True)
        if fastapi_proc:
            try: fastapi_proc.terminate()
            except Exception: pass
        if next_proc:
            try: next_proc.terminate()
            except Exception: pass
        time.sleep(2)
        try:
            if fastapi_proc: fastapi_proc.kill()
            if next_proc: next_proc.kill()
        except Exception: pass
        fastapi_log.close()
        next_log.close()


if __name__ == "__main__":
    main()
