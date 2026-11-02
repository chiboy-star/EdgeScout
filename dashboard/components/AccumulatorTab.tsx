"use client";

import React, { useState } from "react";
import { 
  Layers, 
  Plus, 
  Trash2, 
  AlertTriangle, 
  Info, 
  HelpCircle,
  TrendingDown
} from "lucide-react";

interface Leg {
  id: string;
  match_id: string;
  match_name: string;
  selection: string;
  odds: number;
  margin_pct: number;
}

export function AccumulatorTab() {
  const [legs, setLegs] = useState<Leg[]>([
    { id: "1", match_id: "m_1", match_name: "Arsenal vs Chelsea", selection: "H", odds: 1.75, margin_pct: 5.3 },
    { id: "2", match_id: "m_2", match_name: "Real Madrid vs Sevilla", selection: "H", odds: 1.45, margin_pct: 5.3 },
    { id: "3", match_id: "m_3", match_name: "Inter vs Juventus", selection: "D", odds: 3.20, margin_pct: 5.3 },
    { id: "4", match_id: "m_4", match_name: "Bayern vs Dortmund", selection: "H", odds: 1.60, margin_pct: 5.3 },
  ]);
  const [stake, setStake] = useState<number>(1000);

  const addLeg = () => {
    const newId = String(Date.now());
    setLegs([
      ...legs,
      { id: newId, match_id: `custom_${newId}`, match_name: `Custom Match ${legs.length + 1}`, selection: "H", odds: 2.00, margin_pct: 5.3 }
    ]);
  };

  const removeLeg = (id: string) => {
    setLegs(legs.filter(l => l.id !== id));
  };

  const updateLeg = (id: string, field: keyof Leg, value: any) => {
    setLegs(legs.map(l => l.id === id ? { ...l, [field]: value } : l));
  };

  // Check for correlated legs (same match_name or match_id)
  const matchNames = legs.map(l => l.match_name.trim().toLowerCase());
  const hasCorrelation = new Set(matchNames).size < matchNames.length;

  // Compounding accumulator math audit:
  // M = \prod(1 + m_i) - 1
  // Expected loss = 1 - 1 / (1 + M)
  const combinedOdds = legs.reduce((acc, leg) => acc * (leg.odds > 0 ? leg.odds : 1), 1.0);
  
  let prodOverround = 1.0;
  let singleTotalExpectedLoss = 0;
  const singleStake = legs.length > 0 ? stake / legs.length : 0;

  legs.forEach(leg => {
    const m = leg.margin_pct / 100.0;
    prodOverround *= (1.0 + m);
    // Single bet loss = singleStake * (1 - 1/(1+m))
    singleTotalExpectedLoss += singleStake * (1.0 - 1.0 / (1.0 + m));
  });

  const M = prodOverround - 1.0;
  const combinedOverroundPct = M * 100.0;
  const expectedLossFraction = Math.max(0.0, 1.0 - (1.0 / (1.0 + M)));
  const expectedLossPct = expectedLossFraction * 100.0;
  const expectedLossAmount = stake * expectedLossFraction;
  const trueCombinedProbPct = combinedOdds > 0 ? ((1.0 - expectedLossFraction) / combinedOdds) * 100.0 : 0;

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-bg-900 border border-border-dark rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h3 className="font-display font-bold text-text-primary text-base flex items-center gap-2">
            <Layers className="w-4 h-4 text-lemon" />
            Accumulator Cost & Compounding Friction Calculator
          </h3>
          <p className="text-xs text-text-muted mt-0.5">
            Bookmaker margin compounds multiplicatively with each additional leg. Every added selection drastically decreases your expected return.
          </p>
        </div>

        <button
          onClick={addLeg}
          className="px-3 py-2 bg-lemon hover:bg-lemon/90 text-bg-950 font-medium text-xs rounded-lg transition-all flex items-center gap-1.5 self-start md:self-auto cursor-pointer"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Add Accumulator Leg</span>
        </button>
      </div>

      {/* Correlated Leg Alert */}
      {hasCorrelation && (
        <div className="bg-coral/10 border border-coral/30 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-coral shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <h4 className="font-display font-semibold text-coral text-xs">
              CORRELATED-LEG WARNING DETECTED
            </h4>
            <p className="text-[11px] text-text-muted">
              Multiple legs share the same match. Bookmakers either disallow correlated multiples or apply substantial adverse dependency adjustments because match events are not independent.
            </p>
          </div>
        </div>
      )}

      {/* Main Analysis Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-bg-900 border border-border-dark rounded-xl p-4 space-y-1">
          <span className="text-[10px] text-text-muted font-mono uppercase block">Combined Accumulator Odds</span>
          <div className="font-display font-bold text-lemon text-xl tabular-nums">
            {combinedOdds.toFixed(2)}
          </div>
          <span className="text-[10px] text-text-muted font-mono">
            {legs.length} legs multiplied
          </span>
        </div>

        <div className="bg-bg-900 border border-border-dark rounded-xl p-4 space-y-1">
          <span className="text-[10px] text-text-muted font-mono uppercase block">Compounded Overround (M)</span>
          <div className="font-display font-bold text-coral text-xl tabular-nums">
            +{combinedOverroundPct.toFixed(1)}%
          </div>
          <span className="text-[10px] text-text-muted font-mono">
            ∏(1 + m_i) - 1
          </span>
        </div>

        <div className="bg-bg-900 border border-border-dark rounded-xl p-4 space-y-1">
          <span className="text-[10px] text-text-muted font-mono uppercase block">Audited Expected Loss</span>
          <div className="font-display font-bold text-coral text-xl tabular-nums">
            {expectedLossPct.toFixed(1)}%
          </div>
          <span className="text-[10px] text-text-muted font-mono">
            ₦{expectedLossAmount.toFixed(0)} per ₦{stake.toLocaleString()}
          </span>
        </div>

        <div className="bg-bg-900 border border-border-dark rounded-xl p-4 space-y-1">
          <span className="text-[10px] text-text-muted font-mono uppercase block">True Fair Probability</span>
          <div className="font-display font-bold text-lavender text-xl tabular-nums">
            {trueCombinedProbPct < 0.1 ? "<0.1%" : `${trueCombinedProbPct.toFixed(2)}%`}
          </div>
          <span className="text-[10px] text-text-muted font-mono">
            Market-implied win probability
          </span>
        </div>
      </div>

      {/* Math Explanation & Side-by-Side Comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Legs Editor */}
        <div className="lg:col-span-2 bg-bg-900 border border-border-dark rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-border-dark">
            <h4 className="font-display font-semibold text-sm text-text-primary">Accumulator Selections</h4>
            <div className="flex items-center gap-2">
              <span className="text-xs text-text-muted">Total Stake:</span>
              <div className="flex items-center bg-bg-950 border border-border-dark rounded px-2 py-1">
                <span className="text-xs text-text-muted mr-1">₦</span>
                <input
                  type="number"
                  min="100"
                  step="500"
                  value={stake}
                  onChange={(e) => setStake(Math.max(100, parseFloat(e.target.value) || 100))}
                  className="w-20 bg-transparent text-xs text-text-primary font-mono focus:outline-none"
                />
              </div>
            </div>
          </div>

          <div className="space-y-2.5">
            {legs.map((leg, index) => (
              <div
                key={leg.id}
                className="bg-bg-950/80 border border-border-dark rounded-lg p-3 flex flex-wrap items-center justify-between gap-3 text-xs"
              >
                <div className="flex items-center gap-2 flex-1 min-w-[200px]">
                  <span className="font-mono text-lemon text-[11px] font-bold">#{index + 1}</span>
                  <input
                    type="text"
                    value={leg.match_name}
                    onChange={(e) => updateLeg(leg.id, "match_name", e.target.value)}
                    placeholder="Match Name"
                    className="bg-transparent border-b border-border-dark focus:border-lemon text-text-primary text-xs px-1 py-0.5 w-full focus:outline-none"
                  />
                </div>

                <div className="flex items-center gap-3">
                  <div>
                    <span className="text-[10px] text-text-muted block">Selection</span>
                    <select
                      value={leg.selection}
                      onChange={(e) => updateLeg(leg.id, "selection", e.target.value)}
                      className="bg-bg-900 border border-border-dark rounded px-1.5 py-0.5 text-xs text-text-primary font-mono focus:outline-none"
                    >
                      <option value="H">Home</option>
                      <option value="D">Draw</option>
                      <option value="A">Away</option>
                    </select>
                  </div>

                  <div>
                    <span className="text-[10px] text-text-muted block">Odds</span>
                    <input
                      type="number"
                      step="0.05"
                      min="1.01"
                      value={leg.odds}
                      onChange={(e) => updateLeg(leg.id, "odds", Math.max(1.01, parseFloat(e.target.value) || 1.01))}
                      className="w-16 bg-bg-900 border border-border-dark rounded px-1.5 py-0.5 text-xs text-text-primary font-mono focus:outline-none text-right font-bold text-lemon"
                    />
                  </div>

                  <div>
                    <span className="text-[10px] text-text-muted block">Margin %</span>
                    <input
                      type="number"
                      step="0.1"
                      min="1.0"
                      value={leg.margin_pct}
                      onChange={(e) => updateLeg(leg.id, "margin_pct", Math.max(1.0, parseFloat(e.target.value) || 1.0))}
                      className="w-16 bg-bg-900 border border-border-dark rounded px-1.5 py-0.5 text-xs text-text-muted font-mono focus:outline-none text-right"
                    />
                  </div>

                  <button
                    onClick={() => removeLeg(leg.id)}
                    disabled={legs.length <= 1}
                    className="p-1 text-text-muted hover:text-coral transition-colors disabled:opacity-30 mt-3"
                    title="Remove Leg"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Audited Comparison Box */}
        <div className="bg-bg-900 border border-border-dark rounded-xl p-4 space-y-4 flex flex-col justify-between">
          <div className="space-y-3">
            <h4 className="font-display font-semibold text-sm text-text-primary flex items-center gap-1.5">
              <TrendingDown className="w-4 h-4 text-coral" />
              Compounding Reality Check
            </h4>

            {/* Formula Tooltip Callout */}
            <div className="bg-bg-950 p-3 rounded-lg border border-border-dark text-[11px] space-y-1.5">
              <div className="font-mono text-lemon text-[10px] uppercase font-bold">Audited Formula:</div>
              <div className="font-mono text-text-primary bg-bg-900 px-2 py-1 rounded border border-border-dark">
                Loss = 1 - 1 / (1 + M)
              </div>
              <p className="text-text-muted text-[10px] leading-relaxed">
                Where M = ∏(1 + m_i) - 1. For {legs.length} legs @ {legs[0]?.margin_pct || 5.3}% margin each, total compounded bookmaker friction takes <strong className="text-coral">{expectedLossPct.toFixed(1)}%</strong> of your stake upfront.
              </p>
            </div>

            {/* Comparison */}
            <div className="space-y-2 pt-1">
              <div className="text-xs font-medium text-text-primary">Same ₦{stake.toLocaleString()} Stake:</div>
              
              <div className="p-2.5 bg-bg-950 rounded-lg border border-border-dark flex items-center justify-between text-xs">
                <span className="text-text-muted">Split across {legs.length} singles:</span>
                <span className="font-mono font-semibold text-text-primary">
                  -₦{singleTotalExpectedLoss.toFixed(0)} ({legs[0]?.margin_pct.toFixed(1)}%)
                </span>
              </div>

              <div className="p-2.5 bg-coral/10 rounded-lg border border-coral/30 flex items-center justify-between text-xs">
                <span className="text-coral font-medium">As this {legs.length}-leg accumulator:</span>
                <span className="font-mono font-bold text-coral">
                  -₦{expectedLossAmount.toFixed(0)} ({expectedLossPct.toFixed(1)}%)
                </span>
              </div>
            </div>
          </div>

          <div className="text-[10px] text-text-muted italic border-t border-border-dark pt-2">
            Tip: Bookmakers actively advertise accumulators because compounding margin guarantees the house a far higher expected edge than singles.
          </div>
        </div>
      </div>
    </div>
  );
}

