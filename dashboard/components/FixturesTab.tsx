"use client";

import React, { useState } from "react";
import { FixtureItem } from "../lib/api";
import { 
  Calendar, 
  Filter, 
  HelpCircle, 
  SlidersHorizontal, 
  ShieldAlert,
  Info,
  Clock,
  RotateCcw,
  Sparkles
} from "lucide-react";

interface FixturesTabProps {
  fixtures: FixtureItem[];
  loading: boolean;
  onOpenCustomOdds: (prefill?: any) => void;
  onRefresh?: () => void;
}

export function FixturesTab({
  fixtures,
  loading,
  onOpenCustomOdds,
  onRefresh,
}: FixturesTabProps) {
  const [selectedLeague, setSelectedLeague] = useState<string>("ALL");
  const [timeFilter, setTimeFilter] = useState<"ALL" | "TODAY" | "FAVOURITES" | "CONTESTED" | "LONGSHOTS" | "AWAITING">("ALL");

  if (loading && fixtures.length === 0) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-20 bg-bg-900 border border-border-dark rounded-xl" />
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map(i => (
            <div key={i} className="h-44 bg-bg-900 border border-border-dark rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  const leagues = ["ALL", ...Array.from(new Set(fixtures.map(f => f.league).filter(Boolean)))];

  // Apply filters
  let filtered = selectedLeague === "ALL" 
    ? fixtures 
    : fixtures.filter(f => f.league === selectedLeague);

  if (timeFilter === "TODAY") {
    filtered = filtered.filter(f => f.is_today);
  } else if (timeFilter === "FAVOURITES") {
    filtered = filtered.filter(f => f.category === "Market Favourite");
  } else if (timeFilter === "CONTESTED") {
    filtered = filtered.filter(f => f.category === "Contested");
  } else if (timeFilter === "LONGSHOTS") {
    filtered = filtered.filter(f => f.category === "Longshot");
  } else if (timeFilter === "AWAITING") {
    filtered = filtered.filter(f => !f.has_odds);
  }

  const todayCount = fixtures.filter(f => f.is_today).length;
  const weekCount = fixtures.filter(f => f.is_this_week).length;

  return (
    <div className="space-y-6">
      {/* Top Banner with Filter Chips */}
      <div className="bg-bg-900 border border-border-dark rounded-xl p-4 lg:p-5 space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div>
            <h3 className="font-display font-semibold text-text-primary text-base">
              Market View & Observable Facts (This Week)
            </h3>
            <p className="text-xs text-text-muted mt-0.5">
              Showing upcoming fixtures for the next 7 days with live vig, fair probability, and expected loss. No claims of edge.
            </p>
          </div>

          {/* League Dropdown Filter */}
          <div className="flex items-center gap-2 self-start md:self-auto">
            <Filter className="w-3.5 h-3.5 text-lavender" />
            <span className="text-xs text-text-muted font-mono">League:</span>
            <select
              value={selectedLeague}
              onChange={(e) => setSelectedLeague(e.target.value)}
              className="bg-bg-950 border border-border-dark text-text-primary text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-border-subdued cursor-pointer"
            >
              {leagues.map(l => (
                <option key={l} value={l}>{l}</option>
              ))}
            </select>
          </div>
        </div>

        {/* View / Category Filter Pills (Selected state in Lavender) */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
          <button
            onClick={() => setTimeFilter("ALL")}
            className={`px-3 py-1.5 rounded-lg border font-mono text-[11px] whitespace-nowrap transition-colors cursor-pointer ${
              timeFilter === "ALL"
                ? "bg-lavender/15 text-lavender border-lavender/30"
                : "bg-bg-950 text-text-muted border-border-dark hover:text-text-primary"
            }`}
          >
            All This Week ({weekCount || fixtures.length})
          </button>
          <button
            onClick={() => setTimeFilter("TODAY")}
            className={`px-3 py-1.5 rounded-lg border font-mono text-[11px] whitespace-nowrap transition-colors cursor-pointer ${
              timeFilter === "TODAY"
                ? "bg-lavender/15 text-lavender border-lavender/30"
                : "bg-bg-950 text-text-muted border-border-dark hover:text-text-primary"
            }`}
          >
            Today ({todayCount})
          </button>
          <button
            onClick={() => setTimeFilter("FAVOURITES")}
            className={`px-3 py-1.5 rounded-lg border font-mono text-[11px] whitespace-nowrap transition-colors cursor-pointer ${
              timeFilter === "FAVOURITES"
                ? "bg-lavender/15 text-lavender border-lavender/30"
                : "bg-bg-950 text-text-muted border-border-dark hover:text-text-primary"
            }`}
          >
            Market Favourites (≥65%)
          </button>
          <button
            onClick={() => setTimeFilter("CONTESTED")}
            className={`px-3 py-1.5 rounded-lg border font-mono text-[11px] whitespace-nowrap transition-colors cursor-pointer ${
              timeFilter === "CONTESTED"
                ? "bg-lavender/15 text-lavender border-lavender/30"
                : "bg-bg-950 text-text-muted border-border-dark hover:text-text-primary"
            }`}
          >
            Contested (35–65%)
          </button>
          <button
            onClick={() => setTimeFilter("LONGSHOTS")}
            className={`px-3 py-1.5 rounded-lg border font-mono text-[11px] whitespace-nowrap transition-colors cursor-pointer ${
              timeFilter === "LONGSHOTS"
                ? "bg-lavender/15 text-lavender border-lavender/30"
                : "bg-bg-950 text-text-muted border-border-dark hover:text-text-primary"
            }`}
          >
            Longshots (&lt;20%)
          </button>
          <button
            onClick={() => setTimeFilter("AWAITING")}
            className={`px-3 py-1.5 rounded-lg border font-mono text-[11px] whitespace-nowrap transition-colors cursor-pointer ${
              timeFilter === "AWAITING"
                ? "bg-lavender/15 text-lavender border-lavender/30"
                : "bg-bg-950 text-text-muted border-border-dark hover:text-text-primary"
            }`}
          >
            Awaiting SportyBet Odds
          </button>
        </div>
      </div>

      {/* Main Fixtures Grid or Empty State */}
      {filtered.length === 0 ? (
        <div className="bg-bg-900 border border-border-dark rounded-xl p-8 lg:p-12 text-center space-y-4 max-w-lg mx-auto">
          <div className="w-12 h-12 rounded-full bg-bg-800 border border-border-subdued flex items-center justify-center mx-auto text-lavender">
            <Calendar className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h4 className="font-display font-semibold text-text-primary text-base">
              No Fixtures Found For This Selection
            </h4>
            <p className="text-xs text-text-muted leading-relaxed">
              {timeFilter === "TODAY"
                ? "There are no matches scheduled for today in the selected league. Switch to 'All This Week' or enter custom SportyBet odds below."
                : "No matches match the active category filter for this league. Try clearing filters or entering odds manually."}
            </p>
          </div>
          <div className="flex items-center justify-center gap-3 pt-2">
            <button
              onClick={() => { setSelectedLeague("ALL"); setTimeFilter("ALL"); }}
              className="bg-bg-800 border border-border-subdued text-text-primary px-3 py-1.5 rounded-lg text-xs hover:bg-bg-700 transition-colors cursor-pointer"
            >
              Reset Filters
            </button>
            <button
              onClick={() => onOpenCustomOdds()}
              className="bg-lavender text-bg-950 font-medium px-3.5 py-1.5 rounded-lg text-xs hover:bg-lavender/90 transition-colors cursor-pointer"
            >
              Enter SportyBet Odds
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((f) => (
            <div
              key={f.id}
              className="bg-bg-900 border border-border-dark rounded-xl p-4 hover:border-border-subdued transition-all space-y-3 relative shadow-sm"
            >
              {/* Badges in Top Right */}
              <div className="absolute top-3 right-3 flex items-center gap-1.5">
                {f.is_today && (
                  <span className="text-[9px] font-mono uppercase bg-lemon/15 text-lemon border border-lemon/30 px-1.5 py-0.5 rounded font-bold">
                    TODAY
                  </span>
                )}
                {f.is_demo && (
                  <span className="text-[9px] font-mono uppercase bg-coral/20 text-coral border border-coral/30 px-1.5 py-0.5 rounded font-bold">
                    DEMO
                  </span>
                )}
              </div>

              {/* Match Header */}
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono uppercase text-lavender font-semibold">
                    {f.league}
                  </span>
                  <span className="text-text-muted text-[10px]">•</span>
                  <span className="text-[10px] text-text-muted tabular-nums">
                    {f.utc_date}
                  </span>
                </div>
                <h5 className="font-display font-semibold text-text-primary text-sm mt-0.5 pr-14">
                  {f.match_name}
                </h5>
              </div>

              {/* Odds & True Probabilities Table if Odds Loaded */}
              {f.has_odds && f.odds ? (
                <div className="space-y-2">
                  <div className="grid grid-cols-3 gap-1.5 text-center bg-bg-950/60 p-2 rounded-lg border border-border-dark">
                    <div>
                      <span className="text-[10px] text-text-muted block">Home (1)</span>
                      <span className="font-mono font-bold text-xs text-text-primary">
                        {f.odds.home.toFixed(2)}
                      </span>
                      {f.odds.best_home && f.odds.best_home > f.odds.home && (
                        <span className="text-[9px] text-lemon block font-mono" title={`Best available at ${f.odds.best_home_book}`}>
                          Best: {f.odds.best_home.toFixed(2)}
                        </span>
                      )}
                      {f.shin_probs && (
                        <span className="text-[9px] text-lavender block font-mono">
                          {f.shin_probs.home_pct}%
                        </span>
                      )}
                    </div>
                    <div>
                      <span className="text-[10px] text-text-muted block">Draw (X)</span>
                      <span className="font-mono font-bold text-xs text-text-primary">
                        {f.odds.draw.toFixed(2)}
                      </span>
                      {f.odds.best_draw && f.odds.best_draw > f.odds.draw && (
                        <span className="text-[9px] text-lemon block font-mono" title={`Best available at ${f.odds.best_draw_book}`}>
                          Best: {f.odds.best_draw.toFixed(2)}
                        </span>
                      )}
                      {f.shin_probs && (
                        <span className="text-[9px] text-lavender block font-mono">
                          {f.shin_probs.draw_pct}%
                        </span>
                      )}
                    </div>
                    <div>
                      <span className="text-[10px] text-text-muted block">Away (2)</span>
                      <span className="font-mono font-bold text-xs text-text-primary">
                        {f.odds.away.toFixed(2)}
                      </span>
                      {f.odds.best_away && f.odds.best_away > f.odds.away && (
                        <span className="text-[9px] text-lemon block font-mono" title={`Best available at ${f.odds.best_away_book}`}>
                          Best: {f.odds.best_away.toFixed(2)}
                        </span>
                      )}
                      {f.shin_probs && (
                        <span className="text-[9px] text-lavender block font-mono">
                          {f.shin_probs.away_pct}%
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Market Vig and Expected Cost */}
                  <div className="flex items-center justify-between text-[11px] pt-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] text-text-muted">Consensus Margin:</span>
                      <span className="font-mono font-semibold text-text-primary text-[11px]">
                        {f.margin_pct.toFixed(2)}%
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] text-text-muted">Exp Loss / 1k:</span>
                      <span className="font-mono font-semibold text-coral text-[11px]">
                        ₦{f.expected_loss_per_1000.toFixed(1)}
                      </span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="bg-bg-950/40 border border-dashed border-border-dark rounded-lg p-3 text-center space-y-2">
                  <p className="text-[11px] text-text-muted">
                    No SportyBet odds loaded for this match yet.
                  </p>
                  <button
                    onClick={() => onOpenCustomOdds({
                      match_name: f.match_name,
                      kickoff_utc: f.kickoff_utc
                    })}
                    className="px-2.5 py-1 bg-lavender/10 hover:bg-lavender/20 text-lavender border border-lavender/30 rounded text-[11px] font-medium transition-colors inline-flex items-center gap-1 cursor-pointer"
                  >
                    <SlidersHorizontal className="w-3 h-3" />
                    <span>Enter SportyBet Odds</span>
                  </button>
                </div>
              )}

              {/* Card Footer: Category & Risk Badge */}
              <div className="flex items-center justify-between text-[10px] text-text-muted pt-2 border-t border-border-dark/60">
                <span className="font-mono truncate">{f.dominant_category || f.category}</span>
                <span className="font-mono text-text-muted shrink-0 ml-1">
                  {f.risk_badge}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
