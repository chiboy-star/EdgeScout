"use client";

import React from "react";
import { LedgerSummary } from "../lib/api";
import { 
  TrendingUp, 
  TrendingDown, 
  AlertTriangle, 
  ShieldCheck, 
  PieChart, 
  BarChart3,
  Percent
} from "lucide-react";

interface PerformanceTabProps {
  ledger: LedgerSummary | null;
}

export function PerformanceTab({ ledger }: PerformanceTabProps) {
  const curve = ledger?.bankroll_curve || [];
  const initial = ledger?.initial_bankroll || 100000;
  const current = ledger?.current_bankroll || 100000;
  const totalBets = ledger?.total_bets || 0;
  const settledBets = ledger?.settled_bets || 0;

  // Compute SVG polyline coordinates for bankroll curve
  let minBankroll = initial;
  let maxBankroll = initial;
  curve.forEach(pt => {
    if (pt.bankroll < minBankroll) minBankroll = pt.bankroll;
    if (pt.bankroll > maxBankroll) maxBankroll = pt.bankroll;
  });

  // Margin buffer
  const yRange = Math.max(1000, (maxBankroll - minBankroll) * 1.2);
  const yMid = (maxBankroll + minBankroll) / 2;
  const yMin = yMid - yRange / 2;
  const yMax = yMid + yRange / 2;

  const width = 800;
  const height = 240;

  const points = curve.map((pt, i) => {
    const x = curve.length > 1 ? (i / (curve.length - 1)) * (width - 40) + 20 : width / 2;
    const y = height - 20 - ((pt.bankroll - yMin) / (yMax - yMin)) * (height - 40);
    return `${x},${y}`;
  }).join(" ");

  return (
    <div className="space-y-6">
      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-bg-900 border border-border-dark rounded-xl p-4 space-y-1">
          <span className="text-[10px] text-text-muted font-mono uppercase block">Virtual Capital Growth</span>
          <div className="font-display font-bold text-lemon text-xl tabular-nums">
            ₦{current.toLocaleString()}
          </div>
          <span className="text-xs text-text-muted">
            Initial: ₦{initial.toLocaleString()} ({current >= initial ? "+" : ""}
            {(((current - initial) / initial) * 100).toFixed(2)}%)
          </span>
        </div>

        <div className="bg-bg-900 border border-border-dark rounded-xl p-4 space-y-1">
          <span className="text-[10px] text-text-muted font-mono uppercase block">Execution vs Closing Line (CLV)</span>
          <div className={`font-display font-bold text-xl tabular-nums ${ledger?.mean_clv_pct && ledger.mean_clv_pct >= 0 ? "text-lavender" : "text-coral"}`}>
            {ledger?.mean_clv_pct !== undefined ? `${ledger.mean_clv_pct > 0 ? "+" : ""}${ledger.mean_clv_pct.toFixed(2)}%` : "—"}
          </div>
          <span className="text-xs text-text-muted">
            Beating Close: {ledger?.beating_close_pct?.toFixed(1) ?? "0.0"}% ({ledger?.bets_with_clv ?? 0} bets recorded)
          </span>
        </div>

        <div className="bg-bg-900 border border-border-dark rounded-xl p-4 space-y-1">
          <span className="text-[10px] text-text-muted font-mono uppercase block">Maximum Drawdown</span>
          <div className="font-display font-bold text-coral text-xl tabular-nums">
            -{ledger?.max_drawdown_pct?.toFixed(2) ?? "0.00"}%
          </div>
          <span className="text-xs text-text-muted">
            Peak to trough decline: -₦{ledger?.max_drawdown_amount?.toLocaleString() ?? "0"}
          </span>
        </div>
      </div>

      {/* Bankroll Equity Curve Chart */}
      <div className="bg-bg-900 border border-border-dark rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="font-display font-semibold text-sm text-text-primary">
              Paper Bankroll Equity Trajectory
            </h4>
            <p className="text-[11px] text-text-muted mt-0.5">
              Cumulative virtual balance mapped over sequence of placed and settled bets
            </p>
          </div>
          <span className="text-xs font-mono text-text-muted">
            {curve.length} Trajectory Points
          </span>
        </div>

        {curve.length > 1 ? (
          <div className="relative bg-bg-950 rounded-xl p-4 border border-border-dark overflow-hidden">
            <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-56 overflow-visible">
              {/* Baseline at initial bankroll */}
              <line
                x1="20"
                y1={height - 20 - ((initial - yMin) / (yMax - yMin)) * (height - 40)}
                x2={width - 20}
                y2={height - 20 - ((initial - yMin) / (yMax - yMin)) * (height - 40)}
                stroke="#4A4A52"
                strokeDasharray="4 4"
                strokeWidth="1"
              />
              {/* Trajectory Polyline */}
              <polyline
                fill="none"
                stroke="#E9F56B"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                points={points}
              />
            </svg>
            <div className="flex items-center justify-between text-[10px] text-text-muted font-mono pt-2 border-t border-border-dark/40">
              <span>Bet #0 (Start)</span>
              <span>Baseline: ₦{initial.toLocaleString()}</span>
              <span>Bet #{curve.length - 1}</span>
            </div>
          </div>
        ) : (
          <div className="h-48 bg-bg-950 rounded-xl border border-dashed border-border-dark flex flex-col items-center justify-center text-text-muted text-xs space-y-2">
            <TrendingUp className="w-6 h-6 text-border-subdued" />
            <p>Insufficient ledger history for curve generation.</p>
            <p className="text-[10px] text-text-muted">Place and settle at least 2 bets to chart your bankroll path.</p>
          </div>
        )}
      </div>

      {/* CLV & Integrity Guidance */}
      <div className="bg-bg-900 border border-border-dark rounded-xl p-5 space-y-3">
        <h4 className="font-display font-semibold text-sm text-text-primary flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-lemon" />
          The Single True Benchmark: Closing Line Value (CLV)
        </h4>
        <p className="text-xs text-text-muted leading-relaxed">
          In sports betting, short-term profit and loss are governed by variance (luck). A bettor can lose money over 200 bets while making mathematically sound decisions, or profit over 100 bets through pure fortune. The only recognized empirical indicator of long-term survival is whether your taken odds systematically beat the market closing odds (positive CLV) after bookmaker margins are accounted for.
        </p>
      </div>
    </div>
  );
}
