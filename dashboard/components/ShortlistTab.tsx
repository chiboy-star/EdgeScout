"use client";

import React, { useState } from "react";
import { 
  ShortlistResponse, 
  ShortlistCandidate 
} from "../lib/api";
import { 
  ShieldAlert, 
  ChevronDown, 
  ChevronUp, 
  PlusCircle, 
  Check, 
  Info, 
  AlertCircle,
  HelpCircle,
  SlidersHorizontal,
  ExternalLink
} from "lucide-react";

interface ShortlistTabProps {
  shortlist: ShortlistResponse | null;
  loading: boolean;
  onPlaceBet: (candidate: ShortlistCandidate) => void;
  onOpenCustomOdds: (matchName?: string) => void;
}

export function ShortlistTab({
  shortlist,
  loading,
  onPlaceBet,
  onOpenCustomOdds,
}: ShortlistTabProps) {
  const [expandedFacts, setExpandedFacts] = useState<Record<string, boolean>>({});
  const [placingIds, setPlacingIds] = useState<Record<string, boolean>>({});

  const toggleFacts = (id: string) => {
    setExpandedFacts(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const handleBetClick = async (candidate: ShortlistCandidate) => {
    setPlacingIds(prev => ({ ...prev, [candidate.match_id + candidate.selection]: true }));
    try {
      await onPlaceBet(candidate);
    } finally {
      setPlacingIds(prev => ({ ...prev, [candidate.match_id + candidate.selection]: false }));
    }
  };

  if (loading && !shortlist) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-24 bg-bg-900 border border-border-dark rounded-xl" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-80 bg-bg-900 border border-border-dark rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  const tiers = shortlist?.tiers || { Steady: [], Balanced: [], "Long shot": [] };

  return (
    <div className="space-y-8">
      {/* Persistent Disclaimer Banner */}
      <div className="bg-bg-900/80 border border-border-dark rounded-xl p-4 lg:p-5 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-1.5 h-full bg-lemon" />
        <div className="flex items-start gap-3 pl-2">
          <ShieldAlert className="w-5 h-5 text-lemon shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h3 className="font-display font-semibold text-text-primary text-sm tracking-tight flex items-center gap-2">
              LOWEST-COST PICK, NOT A PREDICTION OF PROFIT
            </h3>
            <p className="text-xs text-text-muted leading-relaxed">
              Bookmaker margin guarantees that the average bet loses money over time. EdgeScout does <strong className="text-text-primary font-medium">not</strong> predict match winners or guarantee profits. Selections below simply minimize expected friction (margin & cost) against the market closing line.
            </p>
          </div>
        </div>
      </div>

      {/* Tier Columns */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Tier 1: Steady */}
        <TierColumn
          title="Steady"
          subtitle="Shin Market Probability ≥ 55%"
          badge="High Implied Prob"
          badgeColor="bg-lemon/10 text-lemon border-lemon/30"
          candidates={tiers.Steady}
          emptyText="No fixtures qualify for the Steady tier today. Market prices do not offer sufficiently low margin or favorable conditions."
          expandedFacts={expandedFacts}
          placingIds={placingIds}
          onToggleFacts={toggleFacts}
          onPlaceBet={handleBetClick}
          onOpenCustomOdds={onOpenCustomOdds}
        />

        {/* Tier 2: Balanced */}
        <TierColumn
          title="Balanced"
          subtitle="Shin Market Probability 35% – 55%"
          badge="Contested"
          badgeColor="bg-lavender/10 text-lavender border-lavender/30"
          candidates={tiers.Balanced}
          emptyText="No fixtures in the Balanced tier meet the cost criteria today."
          expandedFacts={expandedFacts}
          placingIds={placingIds}
          onToggleFacts={toggleFacts}
          onPlaceBet={handleBetClick}
          onOpenCustomOdds={onOpenCustomOdds}
        />

        {/* Tier 3: Long shot */}
        <TierColumn
          title="Long shot"
          subtitle="Shin Market Probability < 20%"
          badge="Hard Stake Cap: 0.25%"
          badgeColor="bg-coral/10 text-coral border-coral/30"
          candidates={tiers["Long shot"]}
          emptyText="No longshot fixtures qualify today. Longshot bias in bookmaker margins typically renders underdog bets high-cost."
          expandedFacts={expandedFacts}
          placingIds={placingIds}
          onToggleFacts={toggleFacts}
          onPlaceBet={handleBetClick}
          onOpenCustomOdds={onOpenCustomOdds}
        />
      </div>
    </div>
  );
}

interface TierColumnProps {
  title: string;
  subtitle: string;
  badge: string;
  badgeColor: string;
  candidates: ShortlistCandidate[];
  emptyText: string;
  expandedFacts: Record<string, boolean>;
  placingIds: Record<string, boolean>;
  onToggleFacts: (id: string) => void;
  onPlaceBet: (candidate: ShortlistCandidate) => void;
  onOpenCustomOdds: (matchName?: string) => void;
}

function TierColumn({
  title,
  subtitle,
  badge,
  badgeColor,
  candidates,
  emptyText,
  expandedFacts,
  placingIds,
  onToggleFacts,
  onPlaceBet,
  onOpenCustomOdds,
}: TierColumnProps) {
  return (
    <div className="flex flex-col space-y-4">
      {/* Tier Header */}
      <div className="bg-bg-900 border border-border-dark rounded-xl p-4 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h4 className="font-display font-bold text-base text-text-primary">{title}</h4>
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${badgeColor}`}>
              {badge}
            </span>
          </div>
          <p className="text-[11px] text-text-muted mt-0.5">{subtitle}</p>
        </div>
        <span className="text-xs font-mono font-semibold px-2 py-1 rounded bg-bg-800 text-text-primary border border-border-dark tabular-nums">
          {candidates.length} / 3
        </span>
      </div>

      {/* Cards List or Empty State */}
      {candidates.length === 0 ? (
        <div className="bg-bg-900/40 border border-dashed border-border-dark rounded-xl p-8 text-center flex flex-col items-center justify-center space-y-2 h-64">
          <Info className="w-6 h-6 text-text-muted" />
          <p className="text-xs font-medium text-text-primary">Tier Empty</p>
          <p className="text-[11px] text-text-muted max-w-xs">{emptyText}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {candidates.map((candidate, idx) => {
            const cardKey = candidate.match_id + candidate.selection;
            const isExpanded = !!expandedFacts[cardKey];
            const isPlacing = !!placingIds[cardKey];

            return (
              <div 
                key={cardKey} 
                className="bg-bg-900 border border-border-dark hover:border-border-subdued rounded-xl p-4 transition-all duration-150 space-y-3.5 relative shadow-sm"
              >
                {/* Demo Badge if demo */}
                {candidate.is_demo && (
                  <span className="absolute top-3 right-3 text-[9px] font-mono uppercase bg-coral/20 text-coral border border-coral/30 px-1.5 py-0.5 rounded font-bold">
                    DEMO
                  </span>
                )}

                {/* Match & League */}
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-lavender font-semibold">
                      {candidate.league}
                    </span>
                    <span className="text-text-muted text-[10px]">•</span>
                    <span className="text-[10px] text-text-muted tabular-nums">
                      {candidate.date}
                    </span>
                  </div>
                  <h5 className="font-display font-semibold text-text-primary text-sm mt-0.5">
                    {candidate.match_name}
                  </h5>
                </div>

                {/* Selection & Odds */}
                <div className="grid grid-cols-2 gap-2 bg-bg-950/60 p-2.5 rounded-lg border border-border-dark">
                  <div>
                    <span className="text-[10px] text-text-muted block">Selection</span>
                    <span className="font-medium text-text-primary text-xs truncate block">
                      {candidate.selection_label}
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] text-text-muted block">Odds Taken</span>
                    <span className="font-mono font-bold text-lemon text-sm tabular-nums">
                      {candidate.odds_taken.toFixed(2)}
                    </span>
                  </div>
                </div>

                {/* Market Probability & Margin Breakdown */}
                <div className="grid grid-cols-3 gap-2 text-center text-[11px] border-t border-border-dark pt-2.5">
                  <div>
                    <span className="text-text-muted text-[10px] block">Shin Market P</span>
                    <span className="font-mono font-semibold text-text-primary tabular-nums">
                      {candidate.shin_market_prob_pct.toFixed(1)}%
                    </span>
                  </div>
                  <div>
                    <span className="text-text-muted text-[10px] block">Margin</span>
                    <span className="font-mono font-semibold text-text-muted tabular-nums">
                      {candidate.bookmaker_margin_pct.toFixed(2)}%
                    </span>
                  </div>
                  <div>
                    <span className="text-text-muted text-[10px] block">Cost / 1k</span>
                    <span className="font-mono font-semibold text-coral tabular-nums">
                      ₦{candidate.expected_cost_per_1000.toFixed(1)}
                    </span>
                  </div>
                </div>

                {/* Odds Freshness & Reference */}
                <div className="flex items-center justify-between text-[10px] text-text-muted pt-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-mono bg-bg-950 px-1.5 py-0.5 rounded border border-border-dark">
                      {candidate.odds_source}
                    </span>
                    {candidate.odds_fetched_time_label && (
                      <span className="font-mono text-text-muted">
                        fetched at {candidate.odds_fetched_time_label}
                      </span>
                    )}
                    {candidate.is_stale ? (
                      <span className="px-1.5 py-0.5 bg-coral/20 text-coral border border-coral/30 rounded font-mono font-bold uppercase text-[9px]">
                        STALE (&gt;24h)
                      </span>
                    ) : (
                      <span className="px-1.5 py-0.5 bg-lemon/10 text-lemon border border-lemon/20 rounded font-mono text-[9px]">
                        Fresh
                      </span>
                    )}
                  </div>
                  <button
                    onClick={() => onOpenCustomOdds(candidate.match_name)}
                    className="text-lavender hover:underline flex items-center gap-1 shrink-0 ml-1"
                  >
                    <span>Check SportyBet</span>
                    <SlidersHorizontal className="w-2.5 h-2.5" />
                  </button>
                </div>

                {/* Suggested Stake & One-Tap Action */}
                <div className="pt-2 border-t border-border-dark flex items-center justify-between gap-2">
                  <div>
                    <span className="text-[10px] text-text-muted block">Suggested Stake</span>
                    <span className="font-mono font-bold text-text-primary text-xs tabular-nums">
                      ₦{candidate.suggested_stake.toLocaleString()}
                    </span>
                    <span className="text-[9px] text-text-muted ml-1">
                      (Cap: {candidate.stake_cap_pct}%)
                    </span>
                  </div>

                  <button
                    onClick={() => onPlaceBet(candidate)}
                    disabled={isPlacing}
                    className="px-3 py-2 bg-lemon hover:bg-lemon/90 text-bg-950 font-medium text-xs rounded-lg transition-all flex items-center gap-1.5 shadow-sm active:scale-95 disabled:opacity-50 cursor-pointer"
                  >
                    <PlusCircle className="w-3.5 h-3.5" />
                    <span>{isPlacing ? "Adding..." : "Add to Ledger"}</span>
                  </button>
                </div>

                {/* Collapsible Supporting Facts */}
                <div className="pt-1">
                  <button
                    onClick={() => onToggleFacts(cardKey)}
                    className="w-full flex items-center justify-between text-[11px] text-text-muted hover:text-text-primary py-1 border-t border-border-dark/60 cursor-pointer"
                  >
                    <span className="font-mono">Supporting Facts & History</span>
                    {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>

                  {isExpanded && (
                    <div className="mt-2 space-y-2 bg-bg-950 p-2.5 rounded-lg border border-border-dark text-[11px]">
                      <div className="flex justify-between">
                        <span className="text-text-muted">Home Form (Last 5):</span>
                        <span className="font-mono font-medium text-text-primary">
                          {candidate.supporting_facts.home_form_last5}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-text-muted">Away Form (Last 5):</span>
                        <span className="font-mono font-medium text-text-primary">
                          {candidate.supporting_facts.away_form_last5}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-text-muted">Head-to-Head (Last 5):</span>
                        <span className="font-mono font-medium text-text-primary">
                          {candidate.supporting_facts.h2h_last5}
                        </span>
                      </div>
                      <div className="border-t border-border-dark pt-1.5 mt-1.5">
                        <div className="text-[10px] text-text-muted font-mono uppercase mb-1">
                          13-Season League Bucket Performance:
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-muted">Bucket:</span>
                          <span className="text-text-primary text-[10px]">{candidate.historical_bucket.bucket_label}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-muted">Sample Size:</span>
                          <span className="font-mono text-text-primary">{candidate.historical_bucket.historical_bets} bets</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-muted">Historical ROI:</span>
                          <span className={`font-mono ${candidate.historical_bucket.historical_roi_pct >= 0 ? "text-lemon" : "text-coral"}`}>
                            {candidate.historical_bucket.historical_roi_pct > 0 ? "+" : ""}
                            {candidate.historical_bucket.historical_roi_pct.toFixed(2)}%
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-muted">95% Bootstrap CI:</span>
                          <span className="font-mono text-text-muted text-[10px]">
                            [{candidate.historical_bucket.roi_ci[1]}%, {candidate.historical_bucket.roi_ci[2]}%]
                          </span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Persistent Card Label */}
                <div className="text-[10px] text-center text-text-muted/80 italic font-mono pt-1">
                  {candidate.pick_label}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

