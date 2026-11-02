"use client";

import React, { useState } from "react";
import { FixtureItem } from "../lib/api";
import { 
  Calendar, 
  Filter, 
  HelpCircle, 
  SlidersHorizontal, 
  ShieldAlert,
  Info
} from "lucide-react";

interface FixturesTabProps {
  fixtures: FixtureItem[];
  loading: boolean;
  onOpenCustomOdds: (matchName?: string) => void;
}

export function FixturesTab({
  fixtures,
  loading,
  onOpenCustomOdds,
}: FixturesTabProps) {
  const [selectedLeague, setSelectedLeague] = useState<string>("ALL");

  if (loading && fixtures.length === 0) {
    return (
      <div className="space-y-4 animate-pulse">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="h-28 bg-bg-900 border border-border-dark rounded-xl" />
        ))}
      </div>
    );
  }

  const leagues = ["ALL", ...Array.from(new Set(fixtures.map(f => f.league)))];
  const filtered = selectedLeague === "ALL" 
    ? fixtures 
    : fixtures.filter(f => f.league === selectedLeague);

  // Group by category
  const favourites = filtered.filter(f => f.category === "Market Favourite");
  const contested = filtered.filter(f => f.category === "Contested");
  const longshots = filtered.filter(f => f.category === "Longshot");

  return (
    <div className="space-y-8">
      {/* Top Banner */}
      <div className="bg-bg-900 border border-border-dark rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h3 className="font-display font-bold text-text-primary text-base">
            Market View & Observable Facts (This Week)
          </h3>
          <p className="text-xs text-text-muted mt-0.5">
            Fixtures and market prices only. No stake suggestions or claims of edge.
          </p>
        </div>

        {/* League Filter */}
        <div className="flex items-center gap-2">
          <Filter className="w-3.5 h-3.5 text-text-muted" />
          <span className="text-xs text-text-muted font-mono">League:</span>
          <select
            value={selectedLeague}
            onChange={(e) => setSelectedLeague(e.target.value)}
            className="bg-bg-950 border border-border-dark text-text-primary text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-border-subdued"
          >
            {leagues.map(l => (
              <option key={l} value={l}>{l}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Sections by Category */}
      <FixtureSection
        title="Market Favourites (≥65% Shin Market Probability)"
        subtitle="Market view, not an edge. High implied probability comes with low odds and steady bookmaker take."
        fixtures={favourites}
        onOpenCustomOdds={onOpenCustomOdds}
      />

      <FixtureSection
        title="Contested Matches (35% – 65% Shin Market Probability)"
        subtitle="Market view, not an edge. Closer margins where neither team is a clear market favourite."
        fixtures={contested}
        onOpenCustomOdds={onOpenCustomOdds}
      />

      <FixtureSection
        title="Market Longshots (<20% Shin Market Probability)"
        subtitle="Market view, not an edge. Longshot bias means bookmaker overrounds are often heaviest on large underdogs."
        fixtures={longshots}
        onOpenCustomOdds={onOpenCustomOdds}
      />
    </div>
  );
}

interface FixtureSectionProps {
  title: string;
  subtitle: string;
  fixtures: FixtureItem[];
  onOpenCustomOdds: (matchName?: string) => void;
}

function FixtureSection({
  title,
  subtitle,
  fixtures,
  onOpenCustomOdds,
}: FixtureSectionProps) {
  if (fixtures.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="border-b border-border-dark pb-2">
        <h4 className="font-display font-semibold text-text-primary text-sm">{title}</h4>
        <p className="text-[11px] text-text-muted mt-0.5">{subtitle}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {fixtures.map(f => (
          <div
            key={f.id}
            className="bg-bg-900 border border-border-dark rounded-xl p-4 hover:border-border-subdued transition-all space-y-3 relative shadow-sm"
          >
            {f.is_demo && (
              <span className="absolute top-3 right-3 text-[9px] font-mono uppercase bg-coral/20 text-coral border border-coral/30 px-1.5 py-0.5 rounded font-bold">
                DEMO
              </span>
            )}

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
              <h5 className="font-display font-semibold text-text-primary text-sm mt-0.5">
                {f.match_name}
              </h5>
            </div>

            {/* Odds Table */}
            <div className="grid grid-cols-3 gap-2 bg-bg-950 p-2 rounded-lg text-center border border-border-dark">
              <div>
                <span className="text-[10px] text-text-muted block">Home</span>
                <span className="font-mono font-bold text-text-primary text-xs tabular-nums">
                  {f.odds.home.toFixed(2)}
                </span>
                <span className="text-[10px] text-text-muted block mt-0.5 font-mono">
                  {f.shin_probs.home_pct.toFixed(0)}%
                </span>
              </div>
              <div>
                <span className="text-[10px] text-text-muted block">Draw</span>
                <span className="font-mono font-bold text-text-primary text-xs tabular-nums">
                  {f.odds.draw.toFixed(2)}
                </span>
                <span className="text-[10px] text-text-muted block mt-0.5 font-mono">
                  {f.shin_probs.draw_pct.toFixed(0)}%
                </span>
              </div>
              <div>
                <span className="text-[10px] text-text-muted block">Away</span>
                <span className="font-mono font-bold text-text-primary text-xs tabular-nums">
                  {f.odds.away.toFixed(2)}
                </span>
                <span className="text-[10px] text-text-muted block mt-0.5 font-mono">
                  {f.shin_probs.away_pct.toFixed(0)}%
                </span>
              </div>
            </div>

            {/* Overround and Friction Cost */}
            <div className="flex items-center justify-between text-xs pt-1 border-t border-border-dark">
              <div>
                <span className="text-[10px] text-text-muted block">Bookmaker Margin</span>
                <span className="font-mono font-semibold text-text-primary text-xs tabular-nums">
                  {f.margin_pct.toFixed(2)}%
                </span>
              </div>
              <div className="text-right">
                <span className="text-[10px] text-text-muted block">Cost / 1,000 Staked</span>
                <span className="font-mono font-semibold text-coral text-xs tabular-nums">
                  ₦{f.expected_loss_per_1000.toFixed(1)}
                </span>
              </div>
            </div>

            {/* Custom Odds Action */}
            <div className="pt-2 border-t border-border-dark flex items-center justify-between">
              <span className="text-[10px] text-text-muted font-mono">{f.odds.source}</span>
              <button
                onClick={() => onOpenCustomOdds(f.match_name)}
                className="text-xs text-lemon hover:underline flex items-center gap-1 font-mono"
              >
                <span>SportyBet Odds</span>
                <SlidersHorizontal className="w-3 h-3" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
