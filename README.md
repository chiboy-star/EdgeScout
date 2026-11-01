# EdgeScout

> Quantitative Football Betting Analysis & Paper-Trading Ledger.  
> **Budget:** $0 (Strictly Free Tiers).  
> **Core Principle:** EdgeScout does **NOT** predict winners or guarantee results. It estimates match outcome probabilities via statistical modeling (Dixon-Coles / bivariate Poisson with time-decay), removes bookmaker margins (using Shin's method or proportional de-vigging), and flags only opportunities where the expected value is positive ($EV > 0$). Skipping a match or generating zero picks is a completely valid and expected output.

---

## Free-Tier Limits & Architecture Table

| Data Provider / Service | Free Tier Allowance | Rate Limit | Quota Window | Architectural Usage & Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **football-data.co.uk** | Unlimited historical CSV archives | Unmetered (fair use) | None | Ingestion of historical results, half-time/full-time scores, opening and closing odds for EPL, La Liga, Serie A, Bundesliga, Ligue 1. Saved as raw files before indexing. |
| **football-data.org** | 12 Tier-1 competitions (EPL, La Liga, Serie A, Bundesliga, Ligue 1, UCL, etc.) | 10 requests / minute | Unmetered under rate limit (100 req/24h if unauthenticated) | Upcoming fixture schedules, current standings, and post-match score settlements. Rate-limited and cached locally. |
| **API-Football (API-Sports)** | 100 requests / day | 10 requests / minute | Resets daily at 00:00 UTC | Lineups, player availability, and injury reports. Managed via a strict budgeter so calls are only spent on shortlisted matches within 60 minutes of kickoff. |
| **OddsPapi** | 250 requests / month *(Legacy free tier; paused for new users)* | 100 requests / hour | Monthly pool | Current odds including regional bookmakers (e.g., SportyBet). Only queried for matches already shortlisted by the mathematical engine. |
| **The Odds API** | 500 credits / month | 30 requests / second | Monthly pool | Aggregated odds from global sharp (Pinnacle) and soft books. Credits cost $\text{markets} \times \text{regions}$; strictly used for final line verification. |
| **Supabase (PostgreSQL)** | 500 MB database, 50k monthly active users | Unmetered pooled connections | Free tier | Production persistence for matches, closing odds, and paper trading ledger (SQLite used for Phase 1). |
| **Vercel** | Free Hobby tier (100 GB bandwidth, serverless functions) | Standard Vercel rate limits | Monthly pool | Next.js frontend dashboard hosting with edge caching and stale-while-revalidate. |
| **GitHub Actions** | 2,000 CI/CD minutes / month | Standard concurrency | Monthly pool | Scheduled cron workflow for daily data pulls, model inference, and paper-trade settlement. |

---

## Directory Layout

```
EdgeScout/
├── edgescout/
│   ├── __init__.py
│   ├── config.py              # Configuration, free-tier limits, thresholds
│   ├── cli.py                 # CLI interface for ingestion and backtesting
│   ├── data/
│   │   ├── fetcher.py         # football-data.co.uk + UCL data fetcher & parser
│   │   ├── storage.py         # SQLite persistence & raw API cache
│   │   └── schemas.py         # Data models and validation
│   ├── models/
│   │   ├── margin.py          # Shin's method & proportional de-vigging
│   │   ├── dixon_coles.py     # Dixon-Coles Poisson model with time decay
│   │   └── kelly.py           # Quarter-Kelly staking & exposure caps
│   └── backtest/
│       ├── walk_forward.py    # Walk-forward engine with strict leakage checks
│       ├── metrics.py         # Log loss, Brier score, calibration, CLV
│       └── reporter.py        # ASCII/Markdown reports & matplotlib plots
├── tests/
│   ├── test_margin.py         # Tests for Shin & proportional margin removal
│   ├── test_kelly.py          # Tests for quarter-Kelly & exposure caps
│   ├── test_leakage.py        # Strict leakage detection & temporal checks
│   └── test_dixon_coles.py    # Dixon-Coles probability calculation tests
├── data/
│   ├── raw/                   # Raw cached CSV responses
│   └── edgescout.sqlite3      # SQLite database
├── reports/
│   ├── backtest_report.md     # Generated backtest report
│   └── plots/                 # Reliability calibration & ROI plots
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## Setup & Installation

### 1. Requirements
- Python 3.11 or Python 3.12 (standard 64-bit distribution).

### 2. Environment Setup
```bash
# Clone the repository and navigate into the workspace
git clone <repo-url>
cd EdgeScout

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux / macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## Running the Engine

### 1. Ingest Historical Matches and Odds
Pulls historical data and closing odds for the 5 major European domestic leagues plus the UEFA Champions League across seasons 2021/22 to 2024/25:

```bash
python -m edgescout.cli ingest --leagues E0,SP1,I1,D1,F1,CL --seasons 2122,2223,2324,2425
```
*Note: All raw downloads are saved directly into `data/raw/` so subsequent runs execute instantly from local cache.*

### 2. Run Walk-Forward Backtesting
Runs chronological out-of-sample walk-forward validation (training only on past matches strictly before each match date, with built-in temporal leakage assertions):

```bash
# Run across all 6 competitions with Shin margin removal
python -m edgescout.cli backtest --devig shin --odds-source b365 --step-days 14

# Or run for a specific league (e.g. English Premier League E0)
python -m edgescout.cli backtest --league E0 --devig shin --odds-source b365 --step-days 14
```

Outputs generated:
- Terminal ASCII summary report.
- High-resolution reliability diagram: `reports/plots/calibration_plot.png`.
- GitHub-flavored markdown report: `reports/backtest_report.md`.

### 3. Run the Test Suite
EdgeScout includes tests verifying mathematical correctness, margin removal properties, Kelly fraction limits, and temporal data leakage prevention:

```bash
python -m pytest -v
```

---

## Evaluation Metrics (Why We Do NOT Headline Accuracy)

In football betting, predicting raw winners or touting a "70% accuracy" headline is mathematically meaningless because win probability is inextricably linked to price. A bettor can have an 80% win rate and lose money, or a 40% win rate and achieve high ROI.

EdgeScout strictly evaluates model quality using proper probabilistic scoring rules:
1. **Multiclass Log Loss (Cross-Entropy):** Penalizes overconfident misclassifications exponentially.
2. **Multiclass Brier Score:** Measures the mean squared deviation between predicted probability vectors and one-hot outcomes.
3. **Probability Calibration (Reliability Diagram & ECE):** Verifies that among events assigned an $x\%$ probability, approximately $x\%$ occur in reality.
4. **Closing Line Value (CLV):** Quantifies whether odds taken beat the sharp closing market ($CLV = \frac{\text{Odds}_{\text{taken}}}{\text{Odds}_{\text{closing}}} - 1$). Consistently beating the closing line is the empirical gold standard for predictive edge.

