# EdgeScout

> Quantitative Football Price-Discipline & Bet-Tracking Workbench.  
> **Budget:** $0 (Strictly Free Tiers).  
> **Core Principle:** EdgeScout does **NOT** predict match winners, claim easy edges, or promote "sure" picks. It is an educational and analytical tool built on the mathematical fact that **bookmaker margins (vig) cause the average bet to lose money**. EdgeScout quantifies the true expected financial cost of bookmaker pricing, removes margins via Shin's model, demonstrates the destructive compounding of accumulator bets, backtests user rules across 13 domestic European seasons (23,459 real matches), and enforces strict paper trading discipline.

---

## Free-Tier Limits & Architecture Table

| Data Provider / Service | Free Tier Allowance | Rate Limit | Quota Window | Architectural Usage & Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **football-data.co.uk** | Unlimited historical CSV archives | Unmetered (fair use) | None | 13 seasons (2012/13 through 2024/25) of results and closing odds for EPL, La Liga, Serie A, Bundesliga, Ligue 1 (23,459 clean matches in SQLite). |
| **football-data.org** | 12 Tier-1 competitions (PL, PD, SA, BL1, FL1, CL, etc.) | 10 requests / minute | Unmetered under rate limit | Live fixture schedules, stable match IDs (`fd_{id}`), and finished score settlements. Rate-limited and cached locally. |
| **SportyBet Manual Odds Entry** | Unlimited / Direct | Real-time | None | Fast manual entry & paste form in the UI. Computes Shin fair probabilities, margin %, and expected loss per ₦1,000 on user-provided prices. |
| **SQLite (Local)** | Local file (`data/edgescout.sqlite3`) | Unmetered local I/O | None | Persistent storage for 23,459 historical matches, paper bankroll, ledger entries with idempotency protection, and `strategy_trials` logging. |
| **Minimal Local Python Server** | Built-in standard library (`edgescout.server`) | Unmetered localhost | None | 0 external dependencies. Serves REST API and unified Luxury Typography UI. |

---

## Phase 3 Capabilities & Modules

### 1. Real Settlement & Stable ID Matching
- **Eliminated Fake/Simulated Results:** Settle entirely from real match scores pulled from football-data.org via stable match IDs (`fd_{id}`).
- **Postponed & Cancelled Game Handling:** Automatically marks matching bets as `VOID` and refunds **100% of the staked bankroll** immediately.
- **Manual Settle Override:** Allows one-click manual settlement (`WON`, `LOST`, `VOID`) for competitions not covered by the free API tier.
- **Closing Odds & CLV Tracking:** Records `odds_taken` on placement and optional `closing_odds` on settlement to track Closing Line Value:
  $$\text{CLV} = \frac{\text{odds\_taken}}{\text{closing\_odds}} - 1$$

### 2. Real Fixtures & Explicit DEMO Badging
- Shows real scheduled matches from football-data.org.
- **"No Odds Loaded" State:** If a match has no odds loaded, it displays a distinct callout with a direct button to input SportyBet decimal odds.
- **Strict Labeling:** Any fixture, outcome, or slate drawn from historical sample or demo data carries a prominent, visible **`DEMO`** badge. No unlabeled demo data anywhere.

### 3. Audited Accumulator Math
- **Audited Expected Loss Formula:**
  $$\text{Expected Loss Fraction} = 1 - \frac{1}{1 + M} \quad \text{where} \quad M = \prod_{i=1}^N (1 + m_i) - 1$$
- **Audit Benchmark:** 4 legs at $5.3\%$ margin each ($m_i = 0.053$):
  $$1 + M = (1.053)^4 \approx 1.22956 \implies M \approx 22.96\%$$
  $$\text{Expected Loss Fraction} = 1 - \frac{1}{1.22956} = 18.67\% \approx 18.7\%$$
  *(Never confuses $M$ with the expected loss fraction).*
- **Correlated Legs Warning:** Flags multi-bets where multiple selections share the same match ID or fixture name, warning that the independent compounding formula does not apply.

### 4. Strategy Tester Integrity
- **Default Split:**
  - **Design (In-Sample):** 2012/13 through 2019/20 (8 seasons, 14,507 matches)
  - **Holdout (Out-of-Sample):** 2020/21 through 2024/25 (5 seasons, 9,546 matches)
  - Shows both side-by-side; **headlines the Holdout split**.
- **Trial Counter Persisted in SQLite (`strategy_trials`):** Every rule tested logs its parameters, design metrics, holdout metrics, and verdict.
- **Multiple-Testing Warning:** Scales dynamically with total trials $N$:
  $$\text{Expected False Positives} \approx 0.05 \times N$$
- **Bookmaker Proxy Caveat:** Bet365 pre-close odds are used as the historical benchmark. Real-world SportyBet margins are $1.0\%-2.5\%$ higher, meaning real-world soft-book losses will exceed these historical figures.
- **Verdict Language:** Stays *"INDISTINGUISHABLE FROM THE MARGIN"* unless the Holdout 95% bootstrap CI is entirely above the margin baseline.

### 5. Unified Frontend
- Next.js has been dropped because `npm run build` failed with `'next' is not recognized as an internal or external command` (dependencies hit continuous network timeouts/resets during download).
- Single, unified frontend maintained in `dashboard/index.html` and served locally via `python -m edgescout.server` on port 8000.

---

## Testing & Verification

All 39 unit tests pass 100% in `pytest`:

```bash
pytest -v
```

Output:
```
============================= 39 passed in 11.25s =============================
```

---

## Running EdgeScout Locally

```bash
# 1. Start local server
python -m edgescout.server

# 2. Open in browser
http://127.0.0.1:8000/
```
Or open `dashboard/index.html` directly in any web browser.
