# EdgeScout

> Quantitative Football Price-Discipline & Bet-Tracking Workbench.  
> **Budget:** $0 (Strictly Free Tiers).  
> **Core Principle:** EdgeScout does **NOT** predict match winners, claim easy edges, or promote "sure" picks. It is an educational and analytical tool built on the mathematical fact that **bookmaker margins (vig) cause the average bet to lose money**. EdgeScout quantifies the true expected financial cost of bookmaker pricing, removes margins via Shin's model, demonstrates the destructive compounding of accumulator bets, backtests user rules across 13 domestic European seasons (23,459 real matches), and enforces strict paper trading discipline.

---

## Free-Tier Limits & Architecture Table

| Data Provider / Service | Free Tier Allowance | Rate Limit | Quota Window | Architectural Usage & Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **football-data.co.uk** | Unlimited historical CSV archives | Unmetered (fair use) | None | 13 seasons (2012/13 through 2024/25) of results and closing odds for EPL, La Liga, Serie A, Bundesliga, Ligue 1 (23,459 clean matches in SQLite). |
| **football-data.org** | 12 Tier-1 competitions | 10 requests / minute | Unmetered under rate limit | Fixture schedules, kickoff calendars, and post-match score settlements. Rate-limited and cached locally. |
| **API-Football (API-Sports)** | 100 requests / day | 10 requests / minute | Resets daily at 00:00 UTC | Lineups, player availability, and injury reports. Budgeted so calls are only spent on shortlisted matches. |
| **SportyBet Manual Odds Entry** | Unlimited / Direct | Real-time | None | Instant manual entry & paste form in the UI. Computes Shin fair probabilities, margin %, and expected loss per ₦1,000 on user-provided prices. |
| **Supabase / SQLite** | SQLite local (Phase 1/2) / 500 MB Postgres free tier | Unmetered pooled connections | Free tier | Persistent storage for 23,459 historical matches, paper bankroll, and ledger entries with idempotency protection. |
| **Vercel** | Free Hobby tier | Standard Vercel rate limits | Monthly pool | Production hosting for Next.js dashboard with edge caching. |

---

## Phase 2 Modules & Capabilities

### 1. Market View (Tab: Today)
- Computes **Shin margin-removed probabilities**, overround %, and expected loss per ₦1,000 staked.
- Categorizes selections into market-implied groups:
  - **Market favourites ($\ge 65\%$)**
  - **Contested ($35 - 65\%$)**
  - **Longshots ($< 20\%$)**
  - Labeled prominently: *"Market view from bookmaker price, NOT an edge."*
- Factual risk badges based on observable margin size and odds skew.
- Fast Manual Odds-Entry Modal for pasting current SportyBet odds.

### 2. Accumulator Cost Calculator (Tab: Accumulator)
- Quantifies the mathematical reality of multi-bets.
- Demonstrates how bookmaker margin compounds exponentially across $N$ events:
  $$\text{Compounded Margin} = \prod_{i=1}^N (1 + m_i) - 1$$
- Computes the true joint probability:
  $$\text{True Joint Probability} = \prod_{i=1}^N p_{\text{fair}, i}$$
- Calculates expected loss per ₦1,000 staked (e.g., losing -₦234 on a 4-leg acca).
- Contrasts with splitting the stake across single bets, which preserves capital by avoiding compound margin extraction.

### 3. Paper Trading Ledger (Tab: Paper Ledger)
- Virtual bankroll tracking (default ₦100,000).
- One-tap "Paper Bet" placement with optimistic UI updates.
- **Double-tap protection:** Enforces unique `idempotency_key` on every paper bet.
- **6-second Undo Window:** Floating toast allows instant bet cancellation and bankroll refund.
- **Staking discipline:** Flat 1% default of current bankroll (₦1,000); optional fractional Kelly stake calculation (capped strictly at 2% single bet and 6% daily total exposure).
- **Persistent Sample Size Warning:** Prominently flagged until at least 300 settled bets exist:
  > *"Sample too small to judge (X / 300 settled bets). Short-term returns are dominated by random variance."*

### 4. Empirical Strategy Tester (Tab: Strategy Tester)
- Backtests custom rule-based betting strategies across **13 real historical seasons** (2012/13 through 2024/25, comprising 23,459 real matches from SQLite).
- Evaluates flat ROI against the bookmaker overround baseline (-4.96%).
- Computes 95% bootstrap confidence intervals (2,000 resamples).
- Provides plain-language statistical verdicts defaulting to:
  > *"INDISTINGUISHABLE FROM THE MARGIN. Outcome is fully explained by normal variance and bookmaker vig."*
- Exposes the severe Favorite-Longshot Bias: betting longshots (> 4.00) yields an ROI of -11.31%, statistically worse than the overround baseline.

---

## Design System: "Luxury Typography"

- **Theme Palette:**
  - Page Background: `#0E0E10` (charcoal-950)
  - Cards & Sheets: `#17171A` (charcoal-900)
  - Raised Surfaces / Hover: `#232327` (charcoal-800)
  - Low-Contrast Borders: `#4A4A52` (charcoal-600)
  - Primary Typography: `#F4F2EA` (warm off-white)
  - Muted Text: `#9A9AA3`
  - Primary Accent: `#E9F56B` (lemon, key numbers, profits)
  - Secondary Accent: `#B49CFF` (lavender, links, badges)
  - Cost / Alert: `#FF7A6B` (expected losses, high vig)
- **Typography:**
  - Headings: `Fraunces` editorial serif.
  - Body: `Inter` sans-serif.
  - Numeric Data: Tabular numbers (`font-mono tabular-nums`) everywhere.
- **Controls & Hotkeys:**
  - `1-6`: Jump to tabs (1: Today, 2: This Week, 3: Acca, 4: Ledger, 5: Strategy, 6: Performance).
  - `⌘K / Ctrl+K`: Universal Command Menu.
  - `Esc`: Close open modals.

---

## Testing & Verification

All 30 unit tests pass across margin models, Kelly caps, leakage prevention, accumulator compounding, paper ledger idempotency, and strategy backtesting:

```bash
# Run full test suite with pytest
pytest -v
```

Output:
```
============================= 30 passed in 3.78s ==============================
```

---

## Running the Dashboard

### Option A: Standalone Interactive Artifact
Open `C:\Users\chine\.gemini\antigravity\brain\a81fc7e1-0852-477c-ba0e-9217794edee6\edgescout_dashboard.html` directly in any web browser or via the Antigravity preview pane.

### Option B: Next.js Production Build
```bash
cd dashboard
npm run build
npm run start
```
