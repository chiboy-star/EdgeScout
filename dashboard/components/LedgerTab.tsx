"use client";

import React, { useState } from "react";
import { LedgerSummary, PaperBet } from "../lib/api";
import { 
  AlertTriangle, 
  RotateCcw, 
  RefreshCw, 
  CheckCircle, 
  XCircle, 
  Clock, 
  TrendingUp, 
  Percent, 
  DollarSign,
  ShieldAlert,
  ArrowUpRight,
  ArrowDownRight,
  Activity,
  Layers
} from "lucide-react";

interface LedgerTabProps {
  ledger: LedgerSummary | null;
  loading: boolean;
  onAutoSettle: () => Promise<void>;
  onManualSettle: (betId: string, outcome: string, closingOdds?: number) => Promise<void>;
  onResetBankroll: () => Promise<void>;
}

export function LedgerTab({
  ledger,
  loading,
  onAutoSettle,
  onManualSettle,
  onResetBankroll,
}: LedgerTabProps) {
  const [settlingAuto, setSettlingAuto] = useState(false);
  const [settlingBetId, setSettlingBetId] = useState<string | null>(null);
  const [closingOddsInput, setClosingOddsInput] = useState<Record<string, string>>({});
  const [activeSubView, setActiveSubView] = useState<"BETS" | "EQUITY">("BETS");

  const handleAutoSettle = async () => {
    setSettlingAuto(true);
    try {
      await onAutoSettle();
    } finally {
      setSettlingAuto(false);
    }
  };

  const handleManual = async (betId: string, outcome: string) => {
    const rawOdds = closingOddsInput[betId];
    const closingOdds = rawOdds ? parseFloat(rawOdds) : undefined;
    setSettlingBetId(betId);
    try {
      await onManualSettle(betId, outcome, closingOdds);
    } finally {
      setSettlingBetId(null);
    }
  };

  if (loading && !ledger) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-32 bg-bg-900 border border-border-dark rounded-xl" />
        <div className="h-64 bg-bg-900 border border-border-dark rounded-xl" />
      </div>
    );
  }

  const bankroll = ledger?.current_bankroll ?? 100000;
  const initial = ledger?.initial_bankroll ?? 100000;
  const pl = ledger?.profit_loss ?? 0;
  const plPct = initial > 0 ? (pl / initial) * 100 : 0;
  const isProfitable = pl >= 0;
  const curve = ledger?.bankroll_curve || [];

  // Compute SVG polyline coordinates for bankroll curve
  let minBankroll = initial;
  let maxBankroll = initial;
  curve.forEach(pt => {
    if (pt.bankroll < minBankroll) minBankroll = pt.bankroll;
    if (pt.bankroll > maxBankroll) maxBankroll = pt.bankroll;
  });

  const yRange = Math.max(1000, (maxBankroll - minBankroll) * 1.2);
  const yMid = (maxBankroll + minBankroll) / 2;
  const yMin = yMid - yRange / 2;
  const yMax = yMid + yRange / 2;

  const width = 800;
  const height = 220;

  const points = curve.map((pt, i) => {
    const x = curve.length > 1 ? (i / (curve.length - 1)) * (width - 40) + 20 : width / 2;
    const y = height - 20 - ((pt.bankroll - yMin) / (yMax - yMin)) * (height - 40);
    return `${x},${y}`;
  }).join(" ");

  return (
    <div className="space-y-6">
      {/* Sample Size Warning */}
      {ledger?.sample_size_warning && (
        <div className="bg-bg-900 border border-border-subdued rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-lemon shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h4 className="font-display font-semibold text-text-primary text-xs tracking-tight">
              SAMPLE SIZE WARNING: {ledger.settled_bets} / 300 BETS SETTLED
            </h4>
            <p className="text-[11px] text-text-muted leading-relaxed">
              Standard error is wide with fewer than 300 settled bets. Luck dominates short-term variance. Do not interpret short-term profit or loss as a persistent edge.
            </p>
          </div>
        </div>
      )}

      {/* Overview Cards (Single Hero Metric in Lemon) */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <div className="bg-bg-900 border border-border-dark rounded-xl p-3.5 space-y-1">
          <span className="text-[10px] text-text-muted font-mono uppercase block">Current Bankroll</span>
          <div className="font-display font-light text-lemon text-xl tabular-nums">
            ₦{bankroll.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <span className="text-[10px] text-text-muted">Start: ₦{initial.toLocaleString()}</span>
        </div>

        <div className="bg-bg-900 border border-border-dark rounded-xl p-3.5 space-y-1">
          <span className="text-[10px] text-text-muted font-mono uppercase block">Total Net P/L</span>
          <div className={`font-display font-semibold text-lg tabular-nums flex items-center gap-1 ${isProfitable ? "text-lavender" : "text-coral"}`}>
            {isProfitable ? <ArrowUpRight className="w-4 h-4 text-lavender" /> : <ArrowDownRight className="w-4 h-4 text-coral" />}
            ₦{pl.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <span className="text-[10px] text-text-muted tabular-nums">({plPct > 0 ? "+" : ""}{plPct.toFixed(2)}%)</span>
        </div>

        <div className="bg-bg-900 border border-border-dark rounded-xl p-3.5 space-y-1">
          <span className="text-[10px] text-text-muted font-mono uppercase block">Settled ROI</span>
          <div className={`font-display font-semibold text-lg tabular-nums ${ledger?.flat_roi_pct && ledger.flat_roi_pct >= 0 ? "text-lavender" : "text-coral"}`}>
            {ledger?.flat_roi_pct !== undefined ? `${ledger.flat_roi_pct > 0 ? "+" : ""}${ledger.flat_roi_pct.toFixed(2)}%` : "0.00%"}
          </div>
          <span className="text-[10px] text-text-muted">Flat Stake</span>
        </div>

        <div className="bg-bg-900 border border-border-dark rounded-xl p-3.5 space-y-1">
          <span className="text-[10px] text-text-muted font-mono uppercase block">Hit Rate</span>
          <div className="font-display font-semibold text-text-primary text-lg tabular-nums">
            {ledger?.hit_rate_pct?.toFixed(1) ?? "0.0"}%
          </div>
          <span className="text-[10px] text-text-muted">
            {ledger?.won_bets ?? 0}W / {ledger?.lost_bets ?? 0}L / {ledger?.void_bets ?? 0}V
          </span>
        </div>

        <div className="bg-bg-900 border border-border-dark rounded-xl p-3.5 space-y-1">
          <span className="text-[10px] text-text-muted font-mono uppercase block">Mean CLV</span>
          <div className={`font-display font-semibold text-lg tabular-nums ${ledger?.mean_clv_pct && ledger.mean_clv_pct >= 0 ? "text-lavender" : "text-coral"}`}>
            {ledger?.mean_clv_pct !== undefined ? `${ledger.mean_clv_pct > 0 ? "+" : ""}${ledger.mean_clv_pct.toFixed(2)}%` : "—"}
          </div>
          <span className="text-[10px] text-text-muted">vs Close ({ledger?.bets_with_clv ?? 0} bets)</span>
        </div>

        <div className="bg-bg-900 border border-border-dark rounded-xl p-3.5 space-y-1">
          <span className="text-[10px] text-text-muted font-mono uppercase block">Max Drawdown</span>
          <div className="font-display font-semibold text-coral text-lg tabular-nums">
            -{ledger?.max_drawdown_pct?.toFixed(2) ?? "0.00"}%
          </div>
          <span className="text-[10px] text-text-muted tabular-nums">
            -₦{ledger?.max_drawdown_amount?.toLocaleString() ?? "0"}
          </span>
        </div>
      </div>

      {/* Merged Performance Section: Bankroll Trajectory Chart */}
      <div className="bg-bg-900 border border-border-dark rounded-xl p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border-dark pb-3">
          <div>
            <h4 className="font-display font-semibold text-sm text-text-primary flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-lavender" />
              <span>Paper Bankroll Equity Trajectory & Analytics</span>
            </h4>
            <p className="text-[11px] text-text-muted mt-0.5">
              Cumulative balance mapped over sequence of bets, tracking execution against closing prices
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono text-text-muted">
              Beating Close: <strong className="text-lavender">{ledger?.beating_close_pct?.toFixed(1) ?? "0.0"}%</strong>
            </span>
          </div>
        </div>

        {/* SVG Equity Curve */}
        {curve.length > 1 ? (
          <div className="relative w-full overflow-hidden">
            <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-44 overflow-visible">
              <line x1="20" y1="20" x2={width - 20} y2="20" stroke="#232327" strokeDasharray="4" />
              <line x1="20" y1={height / 2} x2={width - 20} y2={height / 2} stroke="#232327" strokeDasharray="4" />
              <line x1="20" y1={height - 20} x2={width - 20} y2={height - 20} stroke="#232327" strokeDasharray="4" />
              <polyline
                fill="none"
                stroke="#B49CFF"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                points={points}
              />
            </svg>
            <div className="flex justify-between text-[10px] font-mono text-text-muted pt-1">
              <span>Bet #0 (Start ₦{initial.toLocaleString()})</span>
              <span>Bet #{curve.length - 1} (Current ₦{bankroll.toLocaleString()})</span>
            </div>
          </div>
        ) : (
          <div className="h-28 bg-bg-950/60 border border-dashed border-border-dark rounded-lg flex flex-col items-center justify-center text-center p-4">
            <Activity className="w-5 h-5 text-text-muted mb-1" />
            <p className="text-xs text-text-muted">
              Equity curve will render as paper bets are placed and settled.
            </p>
          </div>
        )}
      </div>

      {/* Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-bg-900 border border-border-dark rounded-xl p-4">
        <div className="flex items-center gap-2">
          <span className="text-xs text-text-muted font-mono">
            Total Bets: <strong className="text-text-primary">{ledger?.total_bets ?? 0}</strong> ({ledger?.open_bets ?? 0} open)
          </span>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleAutoSettle}
            disabled={settlingAuto}
            className="px-3.5 py-2 bg-lavender hover:bg-lavender/90 text-bg-950 font-medium text-xs rounded-lg transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50 shadow-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${settlingAuto ? "animate-spin" : ""}`} />
            <span>{settlingAuto ? "Settling..." : "Auto-Settle Feed"}</span>
          </button>

          <button
            onClick={onResetBankroll}
            className="px-3 py-2 bg-bg-950 hover:bg-bg-800 border border-border-dark text-coral text-xs rounded-lg transition-all flex items-center gap-1.5 cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reset Bankroll</span>
          </button>
        </div>
      </div>

      {/* Bets Ledger Table */}
      <div className="bg-bg-900 border border-border-dark rounded-xl overflow-hidden shadow-sm">
        <div className="p-4 border-b border-border-dark flex items-center justify-between">
          <h4 className="font-display font-semibold text-sm text-text-primary">Ledger Records</h4>
          <span className="text-xs text-text-muted font-mono">Disciplined paper trading ledger</span>
        </div>

        {ledger?.bets && ledger.bets.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-bg-950/80 text-text-muted font-mono text-[10px] uppercase border-b border-border-dark">
                <tr>
                  <th className="py-3 px-4">Date / Match</th>
                  <th className="py-3 px-3">Selection</th>
                  <th className="py-3 px-3">Odds Taken</th>
                  <th className="py-3 px-3">Closing Odds</th>
                  <th className="py-3 px-3">CLV</th>
                  <th className="py-3 px-3">Stake</th>
                  <th className="py-3 px-3">Status</th>
                  <th className="py-3 px-3">Net P/L</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-dark/60 font-mono">
                {ledger.bets.map((bet) => {
                  const isOpen = bet.status === "OPEN";
                  const isWon = bet.status === "WON";
                  const isLost = bet.status === "LOST";
                  const isSettling = settlingBetId === bet.id;

                  return (
                    <tr key={bet.id} className="hover:bg-bg-800/40 transition-colors">
                      <td className="py-3 px-4">
                        <div className="font-medium text-text-primary font-sans">{bet.match_name}</div>
                        <div className="text-[10px] text-text-muted flex items-center gap-1.5">
                          <span>{bet.league_code}</span>
                          <span>•</span>
                          <span className="tabular-nums">{bet.placed_at || bet.created_at || "—"}</span>
                        </div>
                      </td>
                      <td className="py-3 px-3">
                        <span className="px-2 py-0.5 rounded bg-bg-950 border border-border-dark text-[11px] font-bold">
                          {bet.selection}
                        </span>
                      </td>
                      <td className="py-3 px-3 font-bold text-text-primary tabular-nums">
                        {bet.odds_taken.toFixed(2)}
                      </td>
                      <td className="py-3 px-3">
                        {isOpen ? (
                          <input
                            type="number"
                            step="0.01"
                            placeholder="Close"
                            value={closingOddsInput[bet.id] ?? ""}
                            onChange={(e) => setClosingOddsInput({ ...closingOddsInput, [bet.id]: e.target.value })}
                            className="w-16 bg-bg-950 border border-border-dark rounded px-1.5 py-0.5 text-xs text-text-primary focus:outline-none focus:border-border-subdued tabular-nums"
                          />
                        ) : (
                          <span className="text-text-muted tabular-nums">
                            {bet.closing_odds ? bet.closing_odds.toFixed(2) : "—"}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-3">
                        {(() => {
                          const clvVal = bet.clv_percent ?? (bet.clv !== null && bet.clv !== undefined ? bet.clv * 100 : null);
                          return clvVal !== null ? (
                            <span className={`tabular-nums font-semibold ${clvVal >= 0 ? "text-lavender" : "text-coral"}`}>
                              {clvVal > 0 ? "+" : ""}{clvVal.toFixed(1)}%
                            </span>
                          ) : (
                            <span className="text-text-muted">—</span>
                          );
                        })()}
                      </td>
                      <td className="py-3 px-3 text-text-primary tabular-nums">
                        ₦{bet.stake.toLocaleString()}
                      </td>
                      <td className="py-3 px-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${
                          isOpen 
                            ? "bg-bg-950 text-text-muted border-border-dark" 
                            : isWon 
                            ? "bg-lavender/15 text-lavender border-lavender/30" 
                            : isLost 
                            ? "bg-coral/15 text-coral border-coral/30" 
                            : "bg-bg-800 text-text-muted border-border-dark"
                        }`}>
                          {bet.status}
                        </span>
                      </td>
                      <td className="py-3 px-3 tabular-nums font-semibold">
                        {isOpen ? (
                          <span className="text-text-muted">—</span>
                        ) : (
                          <span className={bet.profit_loss >= 0 ? "text-lavender" : "text-coral"}>
                            {bet.profit_loss > 0 ? "+" : ""}₦{bet.profit_loss.toFixed(2)}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right">
                        {isOpen ? (
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => handleManual(bet.id, "WON")}
                              disabled={isSettling}
                              className="px-2 py-1 bg-lavender/15 hover:bg-lavender/25 text-lavender border border-lavender/30 rounded text-[10px] font-bold cursor-pointer transition-colors"
                              title="Settle Won"
                            >
                              W
                            </button>
                            <button
                              onClick={() => handleManual(bet.id, "LOST")}
                              disabled={isSettling}
                              className="px-2 py-1 bg-coral/15 hover:bg-coral/25 text-coral border border-coral/30 rounded text-[10px] font-bold cursor-pointer transition-colors"
                              title="Settle Lost"
                            >
                              L
                            </button>
                            <button
                              onClick={() => handleManual(bet.id, "VOID")}
                              disabled={isSettling}
                              className="px-2 py-1 bg-bg-950 hover:bg-bg-800 border border-border-dark text-text-muted rounded text-[10px] cursor-pointer transition-colors"
                              title="Settle Void (refund)"
                            >
                              V
                            </button>
                          </div>
                        ) : (
                          <span className="text-text-muted text-[11px]">Settled</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-12 text-center space-y-3">
            <Clock className="w-8 h-8 text-border-subdued mx-auto" />
            <h5 className="font-display font-medium text-text-primary text-sm">No Paper Bets Placed Yet</h5>
            <p className="text-xs text-text-muted max-w-sm mx-auto">
              Add selections from the Shortlist or enter custom SportyBet odds to begin tracking paper trades and CLV.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
