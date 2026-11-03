/**
 * EdgeScout API Client.
 * Communicates with FastAPI backend via Next.js rewrites (/api/*).
 */

export interface DataHealthStats {
  latest_match_date: string;
  total_db_matches: number;
  fixtures_fetched_at: string;
  fixtures_fetch_time_label: string;
  is_stale: boolean;
  age_hours: number;
  next_kickoff_utc: string | null;
  next_kickoff_wat: string;
  next_countdown: string;
  upcoming_count: number;
}

export interface ShortlistCandidate {
  match_id: string;
  match_name: string;
  home_team?: string;
  away_team?: string;
  league: string;
  league_code: string;
  date?: string;
  kickoff_utc: string;
  kickoff_wat: string;
  kickoff_countdown: string;
  is_today: boolean;
  is_this_week: boolean;
  selection: string;
  selection_label: string;
  odds_taken: number;
  best_bookmaker: string;
  b365_odds: number;
  odds_source?: string;
  shin_market_prob_pct: number;
  bookmaker_margin_pct: number;
  expected_cost_per_1000: number;
  expected_loss_pct: number;
  savings_per_1000_vs_b365: number;
  line_shopping: {
    best_bookmaker: string;
    best_odds: number;
    b365_odds: number;
    cost_best_1000: number;
    cost_b365_1000: number;
    savings_1000: number;
    quotes: Record<string, number>;
  };
  tier: "Steady" | "Balanced" | "Long shot";
  suggested_stake: number | null;
  stake_cap_pct: number;
  supporting_facts: {
    home_form_last5: string;
    home_form_pts?: number;
    away_form_last5: string;
    away_form_pts?: number;
    h2h_last5: string;
    facts_score: number;
    rest_days_home: number;
    rest_days_away: number;
    agreement_flag?: string;
  };
  why_listed: string;
  historical_bucket: {
    bucket_label: string;
    historical_bets: number;
    historical_roi_pct: number;
    roi_ci: [number, number, number];
    hit_rate_pct: number;
  };
  odds_fetched_at?: string;
  odds_fetched_time_label?: string;
  is_stale?: boolean;
  odds_age_hours?: number;
  limited_history?: boolean;
  history_badge?: string;
  pick_label: string;
  is_demo?: boolean;
  prefill?: {
    match_name: string;
    selection: string;
    home_odds: number;
    draw_odds: number;
    away_odds: number;
  };
}

export interface ShortlistResponse {
  tiers: {
    Steady: ShortlistCandidate[];
    Balanced: ShortlistCandidate[];
    "Long shot": ShortlistCandidate[];
  };
  summary: {
    steady_count: number;
    balanced_count: number;
    long_shot_count: number;
    total_shortlisted: number;
    max_per_tier: number;
    bankroll: number;
    label: string;
  };
  scan_summary?: {
    fixtures_scanned: number;
    fixtures_qualified: number;
    skipped_breakdown: Record<string, number>;
    per_day: Record<string, { scanned: number; qualified: number; date_wat: string }>;
  };
  data_health?: DataHealthStats;
}

export interface PaperBet {
  id: string;
  idempotency_key: string;
  match_id: string;
  match_name: string;
  league_code: string;
  selection: string;
  odds_taken: number;
  closing_odds: number | null;
  clv: number | null;
  clv_percent?: number | null;
  stake: number;
  stake_fraction: number;
  status: "OPEN" | "WON" | "LOST" | "VOID" | "UNDONE";
  settlement_type: string | null;
  profit_loss: number;
  placed_at: string;
  created_at?: string;
  settled_at: string | null;
}

export interface LedgerSummary {
  initial_bankroll: number;
  current_bankroll: number;
  profit_loss: number;
  total_bets: number;
  open_bets: number;
  settled_bets: number;
  won_bets: number;
  lost_bets: number;
  void_bets: number;
  hit_rate_pct: number;
  flat_roi_pct: number;
  max_drawdown_pct: number;
  max_drawdown_amount: number;
  mean_clv_pct: number;
  beating_close_pct: number;
  bets_with_clv: number;
  sample_size_warning: boolean;
  warning_message: string | null;
  bets: PaperBet[];
  bankroll_curve: Array<{ bet_index: number; bankroll: number; clv?: number }>;
}

export interface FixtureItem {
  id: string;
  match_id?: string;
  match_name: string;
  home_team?: string;
  away_team?: string;
  league: string;
  league_code?: string;
  kickoff_utc?: string;
  kickoff_wat?: string;
  kickoff_countdown?: string;
  utc_date: string;
  kickoff_time?: string;
  is_today?: boolean;
  is_this_week?: boolean;
  has_odds?: boolean;
  odds?: {
    home: number;
    draw: number;
    away: number;
    source: string;
    best_home?: number;
    best_home_book?: string;
    best_draw?: number;
    best_draw_book?: string;
    best_away?: number;
    best_away_book?: string;
  } | null;
  shin_probs?: {
    home_pct: number;
    draw_pct: number;
    away_pct: number;
  } | null;
  margin_pct: number;
  expected_loss_per_1000: number;
  category: "Market Favourite" | "Contested" | "Longshot" | "Awaiting Odds" | string;
  dominant_category?: string;
  risk_badge: string;
  is_demo?: boolean;
}

export const api = {
  async getDataHealth(): Promise<DataHealthStats> {
    const res = await fetch('/api/health/data', { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch data health stats');
    return res.json();
  },

  async refreshFixtures(): Promise<DataHealthStats> {
    const res = await fetch('/api/fixtures/refresh', { method: 'POST' });
    if (!res.ok) throw new Error('Failed to refresh fixtures cache');
    return res.json();
  },

  async getShortlist(bankroll?: number): Promise<ShortlistResponse> {
    const url = bankroll ? `/api/shortlist?bankroll=${bankroll}` : '/api/shortlist';
    const res = await fetch(url, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch shortlist');
    return res.json();
  },

  async getFixtures(): Promise<{ fixtures: FixtureItem[] }> {
    const res = await fetch('/api/fixtures', { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch fixtures');
    return res.json();
  },

  async getLedger(): Promise<LedgerSummary> {
    const res = await fetch('/api/bets', { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch ledger');
    return res.json();
  },

  async placeBet(data: {
    idempotency_key: string;
    match_id: string;
    match_name: string;
    league_code?: string;
    selection: string;
    odds: number;
    stake?: number;
    user_prob?: number;
    kickoff_utc?: string;
  }): Promise<{ status: string; bet_id?: string; message?: string }> {
    const res = await fetch('/api/bets/place', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const json = await res.json();
    if (!res.ok) {
      const msg = typeof json.detail === 'string' ? json.detail : (json.detail?.message || json.message || 'Failed to place bet');
      throw new Error(msg);
    }
    return json;
  },

  async undoBet(bet_id: string): Promise<any> {
    const res = await fetch('/api/bets/undo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bet_id }),
    });
    return res.json();
  },

  async manualSettle(data: {
    bet_id: string;
    outcome: string;
    closing_odds?: number;
  }): Promise<any> {
    const res = await fetch('/api/settle/manual', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async autoSettle(): Promise<any> {
    const res = await fetch('/api/settle/auto', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    return res.json();
  },

  async resetBankroll(amount = 100000): Promise<any> {
    const res = await fetch('/api/bankroll/reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ amount }),
    });
    return res.json();
  },

  async calculateAccumulator(legs: any[], stake = 1000): Promise<any> {
    const res = await fetch('/api/accumulator', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ legs, stake }),
    });
    return res.json();
  },

  async runStrategy(params: {
    name: string;
    leagues?: string[];
    min_odds: number;
    max_odds: number;
    selections: string[];
    role_filter: string;
    run_type?: string;
  }): Promise<any> {
    const res = await fetch('/api/strategy/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return res.json();
  },

  async getStrategyTrials(): Promise<{ total_trials: number; recent: any[] }> {
    const res = await fetch('/api/strategy/trials', { cache: 'no-store' });
    return res.json();
  },
};

