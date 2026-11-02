"use client";

import React, { useState } from "react";
import { X, Calculator, PlusCircle, AlertCircle } from "lucide-react";

interface ManualOddsModalProps {
  open: boolean;
  onClose: () => void;
  defaultMatchName?: string;
  onPlaceBet: (betData: {
    match_id: string;
    match_name: string;
    selection: string;
    odds: number;
    stake: number;
  }) => Promise<void>;
}

export function ManualOddsModal({
  open,
  onClose,
  defaultMatchName = "Custom Fixture",
  onPlaceBet,
}: ManualOddsModalProps) {
  const [matchName, setMatchName] = useState(defaultMatchName);
  const [homeOdds, setHomeOdds] = useState<string>("2.10");
  const [drawOdds, setDrawOdds] = useState<string>("3.30");
  const [awayOdds, setAwayOdds] = useState<string>("3.40");
  const [selection, setSelection] = useState<string>("H");
  const [stake, setStake] = useState<string>("1000");
  const [submitting, setSubmitting] = useState(false);

  if (!open) return null;

  const h = parseFloat(homeOdds) || 0;
  const d = parseFloat(drawOdds) || 0;
  const a = parseFloat(awayOdds) || 0;
  const valid = h > 1.0 && d > 1.0 && a > 1.0;

  // Simple proportional de-vig for instant calculation
  let overroundPct = 0;
  let fairProbs = [0.33, 0.33, 0.33];
  let expectedCost1000 = 0;

  if (valid) {
    const rawSum = (1 / h) + (1 / d) + (1 / a);
    overroundPct = (rawSum - 1.0) * 100.0;
    fairProbs = [(1 / h) / rawSum, (1 / d) / rawSum, (1 / a) / rawSum];

    const selOdd = selection === "H" ? h : selection === "D" ? d : a;
    const selProb = selection === "H" ? fairProbs[0] : selection === "D" ? fairProbs[1] : fairProbs[2];
    expectedCost1000 = Math.max(0, 1000 * (1.0 - (selProb * selOdd)));
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!valid) return;
    setSubmitting(true);
    const selOdd = selection === "H" ? h : selection === "D" ? d : a;
    try {
      await onPlaceBet({
        match_id: `custom_${Date.now()}`,
        match_name: matchName || "Custom Match",
        selection,
        odds: selOdd,
        stake: parseFloat(stake) || 1000,
      });
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-bg-950/80 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="w-full max-w-md bg-bg-900 border border-border-subdued rounded-2xl shadow-2xl p-5 space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-border-dark">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-lemon/10 text-lemon">
              <Calculator className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-display font-bold text-text-primary text-sm">
                Custom SportyBet Odds Entry
              </h3>
              <p className="text-[11px] text-text-muted">
                Calculate live margin and add directly to paper ledger
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-800"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div>
            <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">
              Match / Event Name
            </label>
            <input
              type="text"
              value={matchName}
              onChange={(e) => setMatchName(e.target.value)}
              placeholder="e.g. Arsenal vs Chelsea"
              required
              className="w-full bg-bg-950 border border-border-dark rounded-lg px-3 py-2 text-text-primary focus:outline-none focus:border-lemon"
            />
          </div>

          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">Home (1)</label>
              <input
                type="number"
                step="0.01"
                min="1.01"
                value={homeOdds}
                onChange={(e) => setHomeOdds(e.target.value)}
                required
                className="w-full bg-bg-950 border border-border-dark rounded-lg px-2.5 py-1.5 font-mono text-lemon font-bold text-right focus:outline-none"
              />
            </div>
            <div>
              <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">Draw (X)</label>
              <input
                type="number"
                step="0.01"
                min="1.01"
                value={drawOdds}
                onChange={(e) => setDrawOdds(e.target.value)}
                required
                className="w-full bg-bg-950 border border-border-dark rounded-lg px-2.5 py-1.5 font-mono text-lemon font-bold text-right focus:outline-none"
              />
            </div>
            <div>
              <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">Away (2)</label>
              <input
                type="number"
                step="0.01"
                min="1.01"
                value={awayOdds}
                onChange={(e) => setAwayOdds(e.target.value)}
                required
                className="w-full bg-bg-950 border border-border-dark rounded-lg px-2.5 py-1.5 font-mono text-lemon font-bold text-right focus:outline-none"
              />
            </div>
          </div>

          {/* Computed Analysis */}
          {valid && (
            <div className="bg-bg-950 p-3 rounded-xl border border-border-dark space-y-2 font-mono text-[11px]">
              <div className="flex justify-between items-center">
                <span className="text-text-muted">Bookmaker Overround:</span>
                <span className="font-bold text-text-primary">+{overroundPct.toFixed(2)}%</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-text-muted">De-vigged Probabilities:</span>
                <span className="text-text-primary">
                  {(fairProbs[0] * 100).toFixed(0)}% / {(fairProbs[1] * 100).toFixed(0)}% / {(fairProbs[2] * 100).toFixed(0)}%
                </span>
              </div>
              <div className="flex justify-between items-center pt-1 border-t border-border-dark">
                <span className="text-text-muted">Friction Cost / 1k:</span>
                <span className="font-bold text-coral">₦{expectedCost1000.toFixed(1)}</span>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 pt-1">
            <div>
              <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">Your Selection</label>
              <select
                value={selection}
                onChange={(e) => setSelection(e.target.value)}
                className="w-full bg-bg-950 border border-border-dark rounded-lg px-2.5 py-1.5 text-text-primary font-mono focus:outline-none"
              >
                <option value="H">Home ({h > 0 ? h.toFixed(2) : "1"})</option>
                <option value="D">Draw ({d > 0 ? d.toFixed(2) : "X"})</option>
                <option value="A">Away ({a > 0 ? a.toFixed(2) : "2"})</option>
              </select>
            </div>
            <div>
              <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">Stake (₦)</label>
              <input
                type="number"
                min="100"
                step="500"
                value={stake}
                onChange={(e) => setStake(e.target.value)}
                required
                className="w-full bg-bg-950 border border-border-dark rounded-lg px-2.5 py-1.5 font-mono text-text-primary focus:outline-none"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={!valid || submitting}
            className="w-full py-2.5 bg-lemon hover:bg-lemon/90 text-bg-950 font-medium text-xs rounded-lg transition-all flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50 mt-2"
          >
            <PlusCircle className="w-4 h-4" />
            <span>{submitting ? "Placing..." : "Add Custom Bet to Ledger"}</span>
          </button>
        </form>
      </div>
    </div>
  );
}
