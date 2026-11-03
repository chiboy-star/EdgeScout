"use client";

import React, { useState } from "react";
import { 
  Database, 
  Clock, 
  CalendarClock, 
  Layers, 
  RotateCw, 
  CheckCircle2, 
  AlertTriangle,
  Info,
  ChevronDown,
  ChevronUp,
  PlusCircle,
  HelpCircle
} from "lucide-react";
import { DataHealthStats } from "../lib/api";

interface DataHealthStripProps {
  stats: DataHealthStats | null;
  loading: boolean;
  onRefreshFixtures: () => Promise<void>;
  onOpenAddCustomFixture?: () => void;
}

export function DataHealthStrip({
  stats,
  loading,
  onRefreshFixtures,
  onOpenAddCustomFixture,
}: DataHealthStripProps) {
  const [refreshing, setRefreshing] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await onRefreshFixtures();
    } finally {
      setRefreshing(false);
    }
  };

  const isStale = stats?.is_stale || false;

  return (
    <div className="bg-bg-950 border-b border-border-dark py-2 px-4 text-xs transition-all">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-2.5">
        {/* Left Section: DB History & Fixtures Freshness */}
        <div className="flex items-center flex-wrap gap-3 sm:gap-4 text-text-muted">
          {/* Latest DB Match */}
          <div className="flex items-center gap-1.5" title="Latest settled match recorded in SQLite history">
            <Database className="w-3.5 h-3.5 text-lavender shrink-0" />
            <span className="text-[11px] font-mono">DB History:</span>
            <span className="font-mono text-text-primary font-medium">
              {stats?.latest_match_date || "1 Nov 2026"}
            </span>
            {stats?.total_db_matches ? (
              <span className="text-[10px] text-text-muted">
                ({stats.total_db_matches.toLocaleString()} matches)
              </span>
            ) : null}
          </div>

          <span className="hidden sm:inline text-border-dark">•</span>

          {/* Fixtures File Freshness */}
          <div className="flex items-center gap-1.5" title="Pre-match odds feed fetch time from football-data.co.uk">
            <Clock className="w-3.5 h-3.5 text-lavender shrink-0" />
            <span className="text-[11px] font-mono">Fixtures Feed:</span>
            <span className="font-mono text-text-primary">
              {stats?.fixtures_fetch_time_label || "10:00 UTC"}
            </span>
            {isStale ? (
              <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase bg-coral/20 text-coral border border-coral/30 flex items-center gap-1">
                <AlertTriangle className="w-2.5 h-2.5" />
                STALE (&gt;24h)
              </span>
            ) : (
              <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-lavender/10 text-lavender border border-lavender/25 flex items-center gap-0.5">
                <CheckCircle2 className="w-2.5 h-2.5" />
                Fresh
              </span>
            )}
          </div>

          {/* Data Provenance Details Toggle */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[11px] font-mono text-lavender hover:underline flex items-center gap-1 cursor-pointer ml-1"
            title="Inspect feed sources, row counts and league coverage"
          >
            <span>{expanded ? "Hide Provenance" : "Data Provenance"}</span>
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
        </div>

        {/* Right Section: Next Kickoff (WAT), Count & Actions */}
        <div className="flex items-center flex-wrap justify-between sm:justify-end gap-2.5 text-text-muted">
          {/* Next Kickoff */}
          <div className="flex items-center gap-1.5" title="Earliest upcoming fixture kickoff time in Africa/Lagos (WAT, UTC+1)">
            <CalendarClock className="w-3.5 h-3.5 text-lavender shrink-0" />
            <span className="text-[11px] font-mono">Next:</span>
            <span className="font-mono text-text-primary font-medium">
              {stats?.next_kickoff_wat || "Tue 3 Nov, 19:45 WAT"}
            </span>
            {stats?.next_countdown && (
              <span className="text-[10px] font-mono text-lavender bg-lavender/10 px-1.5 py-0.5 rounded border border-lavender/20">
                {stats.next_countdown}
              </span>
            )}
          </div>

          <span className="hidden sm:inline text-border-dark">•</span>

          {/* Add Custom Fixture Button */}
          {onOpenAddCustomFixture && (
            <button
              onClick={onOpenAddCustomFixture}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-bg-900 hover:bg-bg-800 border border-border-dark hover:border-lavender text-lavender text-[11px] font-mono transition-colors cursor-pointer shadow-sm active:scale-95"
              title="Add a custom upcoming fixture & odds manually"
            >
              <PlusCircle className="w-3 h-3 text-lavender" />
              <span>Add Fixture</span>
            </button>
          )}

          {/* Refresh Fixtures Button */}
          <button
            onClick={handleRefresh}
            disabled={refreshing || loading}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-bg-900 hover:bg-bg-800 border border-border-dark hover:border-border-subdued text-text-primary text-[11px] font-mono transition-colors disabled:opacity-50 cursor-pointer shadow-sm active:scale-95"
            title="Re-download pre-match fixtures.csv from football-data.co.uk"
          >
            <RotateCw className={`w-3 h-3 text-lavender ${refreshing ? "animate-spin" : ""}`} />
            <span>{refreshing ? "Fetching..." : "Refresh"}</span>
          </button>
        </div>
      </div>

      {/* Expanded Data Provenance & Coverage Drawer */}
      {expanded && (
        <div className="max-w-7xl mx-auto mt-2.5 pt-2.5 border-t border-border-dark/60 grid grid-cols-1 md:grid-cols-3 gap-3 text-[11px] font-mono">
          {/* Column 1: fixtures.csv */}
          <div className="bg-bg-900/90 p-2.5 rounded-lg border border-border-dark space-y-1.5">
            <div className="flex items-center justify-between text-text-primary font-bold">
              <span>football-data.co.uk (Pre-match Odds)</span>
              <span className="text-lemon">{stats?.fixtures_csv_rows ?? 17} rows</span>
            </div>
            <p className="text-[10px] text-text-muted leading-tight">
              Rolling window covering active round (next 24–48h). Weekend major league odds published Thursday/Friday.
            </p>
            {stats?.fixtures_csv_leagues && Object.keys(stats.fixtures_csv_leagues).length > 0 && (
              <div className="pt-1 border-t border-border-dark/40 space-y-0.5 text-[10px]">
                {Object.entries(stats.fixtures_csv_leagues).map(([lName, count]) => (
                  <div key={lName} className="flex justify-between text-text-muted">
                    <span>{lName}:</span>
                    <span className="text-text-primary">{count} matches</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Column 2: football-data.org */}
          <div className="bg-bg-900/90 p-2.5 rounded-lg border border-border-dark space-y-1.5">
            <div className="flex items-center justify-between text-text-primary font-bold">
              <span>football-data.org (Schedule Feed)</span>
              <span className="text-lavender">
                {stats?.football_data_org_key_set ? `${stats.football_data_org_matches ?? 117} matches` : "No API key"}
              </span>
            </div>
            <p className="text-[10px] text-text-muted leading-tight">
              Tier One free plan: Champions League, Premier League, Championship, La Liga, Serie A, Bundesliga, etc.
            </p>
            {stats?.football_data_org_leagues && Object.keys(stats.football_data_org_leagues).length > 0 && (
              <div className="pt-1 border-t border-border-dark/40 space-y-0.5 text-[10px]">
                {Object.entries(stats.football_data_org_leagues).slice(0, 4).map(([cName, count]) => (
                  <div key={cName} className="flex justify-between text-text-muted">
                    <span className="truncate pr-1">{cName}:</span>
                    <span className="text-text-primary">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Column 3: Coverage Limitations & Action */}
          <div className="bg-bg-900/90 p-2.5 rounded-lg border border-border-dark space-y-1.5">
            <div className="flex items-center gap-1 text-text-primary font-bold">
              <Info className="w-3.5 h-3.5 text-lavender" />
              <span>Coverage Limitations</span>
            </div>
            <ul className="text-[10px] text-text-muted space-y-0.5 list-disc pl-3">
              <li>Europa League (EL) is Tier 3 paid on football-data.org.</li>
              <li>Domestic cups (FA Cup, Copa del Rey) not in standard CSV.</li>
              <li>Use the <strong>"Add Fixture"</strong> button to track any custom match.</li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
