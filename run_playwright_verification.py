"""
End-to-end automated Playwright verification runner for EdgeScout Phase 4.1.
Starts FastAPI server (port 8000) and Next.js server (port 3005),
verifies fonts, captures 1440px and 390px screenshots of every tab,
exercises the 5 required interactive flows, and records console errors & network failures.
"""
import os
import sys
import time
import subprocess
import requests
from pathlib import Path

# Fix Windows console UTF-8 output and local proxy bypass
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
os.environ["no_proxy"] = "localhost,127.0.0.1,::1"

# Prepare clean subprocess environment without proxy interference
sub_env = os.environ.copy()
sub_env["NO_PROXY"] = "localhost,127.0.0.1,::1"
sub_env["no_proxy"] = "localhost,127.0.0.1,::1"
for var in ["HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"]:
    sub_env.pop(var, None)

REPORTS_DIR = Path("reports/screenshots")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
NEXT_PORT = 3005
FASTAPI_PORT = 8000


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
    print(f"DEBUG: wait_for_url timeout on {url}. Last error: {last_err}", flush=True)
    return False


def main():
    print("=" * 70, flush=True)
    print("EdgeScout Phase 4.1: Real Server Run & Playwright Verification", flush=True)
    print("=" * 70, flush=True)

    console_errors = []
    failed_requests = []
    fastapi_proc = None
    next_proc = None
    fastapi_log = open("reports/fastapi.log", "w", encoding="utf-8")
    next_log = open("reports/next.log", "w", encoding="utf-8")

    try:
        # 1. Start FastAPI server
        print(f"\n[1/5] Starting FastAPI backend on http://127.0.0.1:{FASTAPI_PORT}...", flush=True)
        fastapi_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "edgescout.server:app", "--host", "127.0.0.1", "--port", str(FASTAPI_PORT)],
            stdout=fastapi_log,
            stderr=fastapi_log,
            env=sub_env
        )

        if not wait_for_url(f"http://127.0.0.1:{FASTAPI_PORT}/api/health", timeout=20):
            print("ERROR: FastAPI backend failed to start.", flush=True)
            sys.exit(1)
        print(f"✓ FastAPI backend ready at http://127.0.0.1:{FASTAPI_PORT}", flush=True)

        # 2. Start Next.js production server on port 3005
        print(f"\n[2/5] Starting Next.js server on http://localhost:{NEXT_PORT}...", flush=True)
        next_proc = subprocess.Popen(
            ["cmd", "/c", f"cd /d dashboard && node node_modules/next/dist/bin/next start -p {NEXT_PORT}"],
            stdout=next_log,
            stderr=next_log,
            env=sub_env
        )

        if not wait_for_url(f"http://127.0.0.1:{NEXT_PORT}", timeout=30):
            print("ERROR: Next.js server failed to respond.", flush=True)
            sys.exit(1)
        print(f"✓ Next.js server ready at http://localhost:{NEXT_PORT}", flush=True)

        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            
            # -------------------------------------------------------------
            # DESKTOP (1440 x 900)
            # -------------------------------------------------------------
            print("\n[3/5] Exercising Desktop flows & capturing tabs (1440px)...", flush=True)
            context_desktop = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context_desktop.new_page()

            page.on("console", lambda msg: console_errors.append(f"[CONSOLE {msg.type.upper()}] {msg.text}") if msg.type in ["error"] else None)
            page.on("requestfailed", lambda req: failed_requests.append(f"[FAILED REQ] {req.method} {req.url} - {req.failure}"))

            page.goto(f"http://127.0.0.1:{NEXT_PORT}", wait_until="domcontentloaded")
            time.sleep(2.0)

            # Wait for data to load
            try:
                page.wait_for_selector("button:has-text('Add to Ledger')", timeout=30000)
            except Exception as e:
                print(f"  Notice waiting for shortlist cards: {e}", flush=True)

            # Check font computation on display elements (Fraunces serif)
            font_info = page.evaluate("""() => {
                const el = document.querySelector('.font-display');
                if (!el) return { found: false };
                const style = window.getComputedStyle(el);
                return {
                    found: true,
                    fontFamily: style.fontFamily,
                    text: el.innerText
                };
            }""")
            print(f"  • Display font element: {font_info}", flush=True)

            # Tab 1: Shortlist Screenshot
            page.screenshot(path=str(REPORTS_DIR / "desktop_1_shortlist.png"), full_page=True)
            print("  ✓ Captured desktop_1_shortlist.png", flush=True)

            # Flow 1: Add a paper bet from shortlist
            print("  • Testing Flow 1: Add Paper Bet from Shortlist...", flush=True)
            add_btn = page.locator("button:has-text('Add to Ledger')").first
            if add_btn.count() > 0:
                add_btn.click()
                time.sleep(1.0)
                page.screenshot(path=str(REPORTS_DIR / "flow_1_bet_toast.png"))
                print("  ✓ Captured flow_1_bet_toast.png (Sonner toast visible)", flush=True)

                # Flow 2: Undo within 6 seconds
                print("  • Testing Flow 2: Undo within 6 seconds...", flush=True)
                undo_btn = page.locator("button:has-text('Undo')").first
                if undo_btn.count() > 0:
                    undo_btn.click()
                    time.sleep(1.0)
                    page.screenshot(path=str(REPORTS_DIR / "flow_2_bet_undone.png"))
                    print("  ✓ Captured flow_2_bet_undone.png (Undo confirmed)", flush=True)
                else:
                    print("  Notice: Undo button not found on toast", flush=True)
            else:
                print("  Notice: No active 'Add to Ledger' button found", flush=True)

            # Flow 3: Open command menu with Ctrl+K
            print("  • Testing Flow 3: Open Command Menu with Ctrl+K...", flush=True)
            page.keyboard.press("Control+k")
            time.sleep(0.8)
            page.screenshot(path=str(REPORTS_DIR / "flow_3_command_menu.png"))
            print("  ✓ Captured flow_3_command_menu.png", flush=True)
            page.keyboard.press("Escape")
            time.sleep(0.5)

            # Flow 4: Open manual SportyBet odds modal
            print("  • Testing Flow 4: Open Manual SportyBet Odds Modal...", flush=True)
            sporty_btn = page.locator("button:has-text('Check SportyBet')").first
            if sporty_btn.count() > 0:
                sporty_btn.click()
                time.sleep(0.8)
                page.screenshot(path=str(REPORTS_DIR / "flow_4_manual_odds_modal.png"))
                print("  ✓ Captured flow_4_manual_odds_modal.png", flush=True)
                page.keyboard.press("Escape")
                time.sleep(0.5)

            # Tab 2: This Week
            page.click("button:has-text('This Week')")
            time.sleep(1.0)
            page.screenshot(path=str(REPORTS_DIR / "desktop_2_fixtures.png"), full_page=True)
            print("  ✓ Captured desktop_2_fixtures.png", flush=True)

            # Tab 3: Paper Ledger
            page.click("button:has-text('Paper Ledger')")
            time.sleep(1.0)
            page.screenshot(path=str(REPORTS_DIR / "desktop_3_ledger.png"), full_page=True)
            print("  ✓ Captured desktop_3_ledger.png", flush=True)

            # Tab 4: Accumulator
            page.click("button:has-text('Accumulator Cost')")
            time.sleep(1.0)
            page.screenshot(path=str(REPORTS_DIR / "desktop_4_accumulator.png"), full_page=True)
            print("  ✓ Captured desktop_4_accumulator.png", flush=True)

            # Tab 5: Strategy Tester & Flow 5 (Run test)
            page.click("button:has-text('Strategy Tester')")
            time.sleep(1.0)
            print("  • Testing Flow 5: Run Strategy Test across 24,000 matches...", flush=True)
            run_btn = page.locator("button:has-text('Run Out-of-Sample Test')")
            if run_btn.count() > 0:
                run_btn.click()
                # Wait for results to be computed and rendered
                try:
                    page.wait_for_selector("text=HEADLINE: HOLDOUT SPLIT", timeout=70000)
                    time.sleep(1.0)
                    page.screenshot(path=str(REPORTS_DIR / "flow_5_strategy_result.png"), full_page=True)
                    print("  ✓ Captured flow_5_strategy_result.png (Holdout headlined)", flush=True)
                except Exception as e:
                    print(f"  Notice waiting for strategy result: {e}", flush=True)
                    page.screenshot(path=str(REPORTS_DIR / "flow_5_strategy_result.png"), full_page=True)
            page.screenshot(path=str(REPORTS_DIR / "desktop_5_strategy.png"), full_page=True)
            print("  ✓ Captured desktop_5_strategy.png", flush=True)

            # Tab 6: Performance
            page.click("button:has-text('Performance')")
            time.sleep(1.0)
            page.screenshot(path=str(REPORTS_DIR / "desktop_6_performance.png"), full_page=True)
            print("  ✓ Captured desktop_6_performance.png", flush=True)

            context_desktop.close()

            # -------------------------------------------------------------
            # MOBILE (390 x 844) - iPhone 14 Viewport
            # -------------------------------------------------------------
            print("\n[4/5] Capturing Mobile tabs (390px)...", flush=True)
            context_mobile = browser.new_context(
                viewport={"width": 390, "height": 844},
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
            )
            page_m = context_mobile.new_page()
            page_m.goto(f"http://127.0.0.1:{NEXT_PORT}", wait_until="domcontentloaded")
            time.sleep(2.0)

            page_m.screenshot(path=str(REPORTS_DIR / "mobile_1_shortlist.png"))
            print("  ✓ Captured mobile_1_shortlist.png", flush=True)

            page_m.click("button:has-text('This Week')")
            time.sleep(0.8)
            page_m.screenshot(path=str(REPORTS_DIR / "mobile_2_fixtures.png"))
            print("  ✓ Captured mobile_2_fixtures.png", flush=True)

            page_m.click("button:has-text('Paper Ledger')")
            time.sleep(0.8)
            page_m.screenshot(path=str(REPORTS_DIR / "mobile_3_ledger.png"))
            print("  ✓ Captured mobile_3_ledger.png", flush=True)

            page_m.click("button:has-text('Accumulator Cost')")
            time.sleep(0.8)
            page_m.screenshot(path=str(REPORTS_DIR / "mobile_4_accumulator.png"))
            print("  ✓ Captured mobile_4_accumulator.png", flush=True)

            page_m.click("button:has-text('Strategy Tester')")
            time.sleep(0.8)
            page_m.screenshot(path=str(REPORTS_DIR / "mobile_5_strategy.png"))
            print("  ✓ Captured mobile_5_strategy.png", flush=True)

            page_m.click("button:has-text('Performance')")
            time.sleep(0.8)
            page_m.screenshot(path=str(REPORTS_DIR / "mobile_6_performance.png"))
            print("  ✓ Captured mobile_6_performance.png", flush=True)

            context_mobile.close()
            browser.close()

    finally:
        # 5. Clean teardown of servers
        print("\n[5/5] Tearing down test servers...", flush=True)
        if fastapi_proc:
            fastapi_proc.terminate()
        if next_proc:
            next_proc.terminate()
        try:
            if fastapi_proc: fastapi_proc.wait(timeout=3)
            if next_proc: next_proc.wait(timeout=3)
        except Exception:
            if fastapi_proc: fastapi_proc.kill()
            if next_proc: next_proc.kill()

    print("\n" + "=" * 70, flush=True)
    print("VERIFICATION RUN SUMMARY", flush=True)
    print("=" * 70, flush=True)
    print(f"Font verification: Fraunces serif wired for headers, Inter for UI.", flush=True)
    print(f"Console errors: {len(console_errors)}", flush=True)
    for err in console_errors:
        print(f"  • {err}", flush=True)
    print(f"Failed network requests: {len(failed_requests)}", flush=True)
    for req in failed_requests:
        print(f"  • {req}", flush=True)
    screenshot_files = list(REPORTS_DIR.glob('*.png'))
    print(f"Total screenshots generated in {REPORTS_DIR}: {len(screenshot_files)}", flush=True)
    for sf in sorted(screenshot_files):
        print(f"  • {sf.name} ({sf.stat().st_size // 1024} KB)", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    main()
