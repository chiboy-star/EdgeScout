"use client";

import React, { useState } from "react";
import { 
  Database, 
  Clock, 
  CalendarClock, 
  Layers, 
  RotateCw, 
  CheckCircle2, 
  AlertTriangle 
} from "lucide-react";
import { DataHealthStats } from "../lib/api";

interface DataHealthStripProps {
  stats: DataHealthStats | null;
  loading: boolean;
  onRefreshFixtures: () => Promise<void>;
}

export function DataHealthStrip({
  stats,
  loading,
  onRefreshFixtures,
}: DataHealthStripProps) {
  const [refreshing, setRefreshing] = useState(false);

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
    <div className="bg-bg-950 border-b border-border-dark py-2 px-4 text-xs">
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
        </div>

        {/* Right Section: Next Kickoff (WAT), Count & Refresh Action */}
        <div className="flex items-center flex-wrap justify-between sm:justify-end gap-3 text-text-muted">
          {/* Next Kickoff */}
          <div className="flex items-center gap-1.5" title="Earliest upcoming fixture kickoff time in Africa/Lagos (WAT, UTC+1)">
            <CalendarClock className="w-3.5 h-3.5 text-lavender shrink-0" />
            <span className="text-[11px] font-mono">Next Kickoff:</span>
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

          {/* Upcoming Count */}
          <div className="flex items-center gap-1.5" title="Matches scheduled for the next 7 days">
            <Layers className="w-3.5 h-3.5 text-lavender shrink-0" />
            <span className="text-[11px] font-mono">Upcoming:</span>
            <span className="font-mono text-text-primary font-semibold tabular-nums">
              {stats?.upcoming_count ?? 9} matches
            </span>
          </div>

          {/* Refresh Fixtures Button */}
          <button
            onClick={handleRefresh}
            disabled={refreshing || loading}
            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-bg-900 hover:bg-bg-800 border border-border-dark hover:border-border-subdued text-text-primary text-[11px] font-mono transition-colors disabled:opacity-50 cursor-pointer shadow-sm active:scale-95"
            title="Re-download pre-match fixtures.csv from football-data.co.uk"
          >
            <RotateCw className={`w-3 h-3 text-lavender ${refreshing ? "animate-spin" : ""}`} />
            <span>{refreshing ? "Fetching..." : "Refresh fixtures"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
