"use client";

import React, { useState, useEffect } from "react";
import { api } from "../lib/api";
import { 
  FlaskConical, 
  Play, 
  AlertTriangle, 
  ShieldAlert, 
  History, 
  CheckCircle, 
  XCircle,
  HelpCircle
} from "lucide-react";

export function StrategyTesterTab() {
  const [ruleName, setRuleName] = useState("Home Favourites (1.50 - 2.00)");
  const [selectedLeagues, setSelectedLeagues] = useState<string[]>(["E0", "SP1", "I1", "D1", "F1"]);
  const [minOdds, setMinOdds] = useState<number>(1.50);
  const [maxOdds, setMaxOdds] = useState<number>(2.00);
  const [selections, setSelections] = useState<string[]>(["H"]);
  const [roleFilter, setRoleFilter] = useState<string>("ALL");

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any | null>(null);
  const [trials, setTrials] = useState<{ total_trials: number; recent: any[] }>({ total_trials: 0, recent: [] });

  const loadTrials = async () => {
    try {
      const data = await api.getStrategyTrials();
      setTrials(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadTrials();
  }, []);

  const handleRun = async () => {
    setLoading(true);
    try {
      const res = await api.runStrategy({
        name: ruleName,
        leagues: selectedLeagues,
        min_odds: minOdds,
        max_odds: maxOdds,
        selections: selections,
        role_filter: roleFilter,
      });
      setResult(res);
      await loadTrials();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const toggleLeague = (code: string) => {
    if (selectedLeagues.includes(code)) {
      if (selectedLeagues.length > 1) setSelectedLeagues(selectedLeagues.filter(l => l !== code));
    } else {
      setSelectedLeagues([...selectedLeagues, code]);
    }
  };

  const toggleSelection = (sel: string) => {
    if (selections.includes(sel)) {
      if (selections.length > 1) setSelections(selections.filter(s => s !== sel));
    } else {
      setSelections([...selections, sel]);
    }
  };

  const expectedFalsePositives = Math.round(0.05 * trials.total_trials * 10) / 10;

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="bg-bg-900 border border-border-dark rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h3 className="font-display font-bold text-text-primary text-base flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-lavender" />
            13-Season Strategy Backtester (Strict Out-of-Sample Split)
          </h3>
          <p className="text-xs text-text-muted mt-0.5">
            Design on 2012/13–2019/20 (8 seasons), hold out 2020/21–2024/25 (5 seasons). We headline the holdout result.
          </p>
        </div>
      </div>

      {/* Multiple Testing Warning */}
      <div className="bg-bg-900 border border-border-subdued rounded-xl p-4 flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-lemon shrink-0 mt-0.5" />
        <div className="space-y-1">
          <h4 className="font-display font-semibold text-text-primary text-xs">
            MULTIPLE-TESTING CAUTION: {trials.total_trials} TOTAL STRATEGY RUNS LOGGED
          </h4>
          <p className="text-[11px] text-text-muted leading-relaxed">
            At {trials.total_trials} rules tested, expect approximately <strong className="text-lemon font-medium">{expectedFalsePositives}</strong> rules to appear profitable purely due to random statistical noise (p &lt; 0.05). Historical backtests run on Bet365 proxy odds; real-world SportyBet margins are almost certainly higher.
          </p>
        </div>
      </div>

      {/* Strategy Builder Form */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 bg-bg-900 border border-border-dark rounded-xl p-4 space-y-4">
          <h4 className="font-display font-semibold text-sm text-text-primary">Rule Configuration</h4>

          <div>
            <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">Rule Name</label>
            <input
              type="text"
              value={ruleName}
              onChange={(e) => setRuleName(e.target.value)}
              className="w-full bg-bg-950 border border-border-dark rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:border-lemon"
            />
          </div>

          <div>
            <label className="text-[10px] text-text-muted font-mono uppercase block mb-1.5">Leagues</label>
            <div className="flex flex-wrap gap-1.5">
              {[
                { code: "E0", label: "EPL" },
                { code: "SP1", label: "La Liga" },
                { code: "I1", label: "Serie A" },
                { code: "D1", label: "Bundesliga" },
                { code: "F1", label: "Ligue 1" },
              ].map(lg => {
                const isSelected = selectedLeagues.includes(lg.code);
                return (
                  <button
                    key={lg.code}
                    onClick={() => toggleLeague(lg.code)}
                    className={`px-2.5 py-1 text-xs rounded-lg font-mono transition-colors ${
                      isSelected
                        ? "bg-lemon text-bg-950 font-bold"
                        : "bg-bg-950 text-text-muted border border-border-dark hover:text-text-primary"
                    }`}
                  >
                    {lg.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">Min Odds</label>
              <input
                type="number"
                step="0.05"
                min="1.01"
                value={minOdds}
                onChange={(e) => setMinOdds(parseFloat(e.target.value) || 1.01)}
                className="w-full bg-bg-950 border border-border-dark rounded-lg px-2.5 py-1.5 text-xs text-text-primary font-mono focus:outline-none"
              />
            </div>
            <div>
              <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">Max Odds</label>
              <input
                type="number"
                step="0.05"
                max="50.0"
                value={maxOdds}
                onChange={(e) => setMaxOdds(parseFloat(e.target.value) || 50.0)}
                className="w-full bg-bg-950 border border-border-dark rounded-lg px-2.5 py-1.5 text-xs text-text-primary font-mono focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="text-[10px] text-text-muted font-mono uppercase block mb-1.5">Selections</label>
            <div className="grid grid-cols-3 gap-2">
              {[
                { code: "H", label: "Home" },
                { code: "D", label: "Draw" },
                { code: "A", label: "Away" },
              ].map(s => {
                const isSelected = selections.includes(s.code);
                return (
                  <button
                    key={s.code}
                    onClick={() => toggleSelection(s.code)}
                    className={`py-1.5 text-xs rounded-lg font-mono transition-colors ${
                      isSelected
                        ? "bg-lavender text-bg-950 font-bold"
                        : "bg-bg-950 text-text-muted border border-border-dark hover:text-text-primary"
                    }`}
                  >
                    {s.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">Market Role</label>
            <select
              value={roleFilter}
              onChange={(e) => setRoleFilter(e.target.value)}
              className="w-full bg-bg-950 border border-border-dark text-text-primary text-xs rounded-lg px-2.5 py-1.5 focus:outline-none"
            >
              <option value="ALL">All Matches</option>
              <option value="FAVOURITES">Market Favourites Only</option>
              <option value="UNDERDOGS">Underdogs Only</option>
            </select>
          </div>

          <button
            onClick={handleRun}
            disabled={loading}
            className="w-full py-2.5 bg-lemon hover:bg-lemon/90 text-bg-950 font-medium text-xs rounded-lg transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50"
          >
            <Play className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>{loading ? "Testing 24,000 Matches..." : "Run Out-of-Sample Test"}</span>
          </button>
        </div>

        {/* Results Pane */}
        <div className="lg:col-span-2 space-y-4">
          {result ? (
            <div className="bg-bg-900 border border-border-dark rounded-xl p-5 space-y-5">
              {/* Headlined Holdout Result */}
              <div className="bg-bg-950 border border-border-subdued rounded-xl p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold text-lemon uppercase tracking-wider">
                    HEADLINE: HOLDOUT SPLIT (2020/21 – 2024/25)
                  </span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border uppercase ${
                    result.verdict_badge.includes("NO") || result.verdict_badge.includes("NEGATIVE")
                      ? "bg-coral/15 text-coral border-coral/30"
                      : "bg-lemon/15 text-lemon border-lemon/30"
                  }`}>
                    {result.verdict_badge}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-3 pt-2">
                  <div>
                    <span className="text-[10px] text-text-muted block">Holdout ROI</span>
                    <span className={`font-display font-bold text-xl tabular-nums ${
                      result.holdout.flat_roi_pct >= 0 ? "text-lemon" : "text-coral"
                    }`}>
                      {result.holdout.flat_roi_pct > 0 ? "+" : ""}{result.holdout.flat_roi_pct.toFixed(2)}%
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-text-muted block">95% Bootstrap CI</span>
                    <span className="font-mono text-xs text-text-primary tabular-nums block mt-1">
                      [{result.holdout.roi_ci[1]}%, {result.holdout.roi_ci[2]}%]
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-text-muted block">Holdout Bets</span>
                    <span className="font-mono font-bold text-text-primary text-sm tabular-nums block mt-1">
                      {result.holdout.total_bets}
                    </span>
                  </div>
                </div>
              </div>

              {/* Side-by-Side Comparison: Design vs Holdout */}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="bg-bg-950 text-text-muted text-[10px] uppercase border-b border-border-dark">
                    <tr>
                      <th className="py-2.5 px-3">Metric</th>
                      <th className="py-2.5 px-3 text-lavender">Design Split (2012-2020)</th>
                      <th className="py-2.5 px-3 text-lemon">Holdout Split (2020-2025)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-dark/60">
                    <tr>
                      <td className="py-2.5 px-3 text-text-muted">Total Matches Evaluated</td>
                      <td className="py-2.5 px-3">{result.design.total_bets}</td>
                      <td className="py-2.5 px-3 font-semibold">{result.holdout.total_bets}</td>
                    </tr>
                    <tr>
                      <td className="py-2.5 px-3 text-text-muted">Hit Rate %</td>
                      <td className="py-2.5 px-3">{result.design.hit_rate_pct.toFixed(1)}%</td>
                      <td className="py-2.5 px-3 font-semibold">{result.holdout.hit_rate_pct.toFixed(1)}%</td>
                    </tr>
                    <tr>
                      <td className="py-2.5 px-3 text-text-muted">Flat Stake ROI</td>
                      <td className={`py-2.5 px-3 ${result.design.flat_roi_pct >= 0 ? "text-lemon" : "text-coral"}`}>
                        {result.design.flat_roi_pct > 0 ? "+" : ""}{result.design.flat_roi_pct.toFixed(2)}%
                      </td>
                      <td className={`py-2.5 px-3 font-bold ${result.holdout.flat_roi_pct >= 0 ? "text-lemon" : "text-coral"}`}>
                        {result.holdout.flat_roi_pct > 0 ? "+" : ""}{result.holdout.flat_roi_pct.toFixed(2)}%
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2.5 px-3 text-text-muted">95% Bootstrap CI</td>
                      <td className="py-2.5 px-3 text-text-muted">
                        [{result.design.roi_ci[1]}%, {result.design.roi_ci[2]}%]
                      </td>
                      <td className="py-2.5 px-3 font-semibold">
                        [{result.holdout.roi_ci[1]}%, {result.holdout.roi_ci[2]}%]
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Honest Verdict Prose */}
              <div className="text-xs text-text-muted bg-bg-950 p-3.5 rounded-lg border border-border-dark space-y-1">
                <span className="font-semibold text-text-primary block font-mono text-[11px] uppercase">
                  Statistical Finding:
                </span>
                <p>{result.verdict_explanation}</p>
              </div>
            </div>
          ) : (
            <div className="bg-bg-900 border border-border-dark rounded-xl p-12 text-center text-text-muted space-y-2">
              <FlaskConical className="w-8 h-8 mx-auto text-border-subdued" />
              <p className="text-xs font-medium text-text-primary">No Strategy Tested Yet</p>
              <p className="text-[11px] max-w-sm mx-auto">
                Configure your rule on the left and run an out-of-sample backtest across 24,000 matches from 13 European league seasons.
              </p>
            </div>
          )}

          {/* Past Trials Log */}
          {trials.recent.length > 0 && (
            <div className="bg-bg-900 border border-border-dark rounded-xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h5 className="font-display font-semibold text-xs text-text-primary flex items-center gap-1.5">
                  <History className="w-3.5 h-3.5 text-lavender" />
                  Recent Preregistered Trials in SQLite
                </h5>
                <span className="text-[10px] text-text-muted font-mono">{trials.total_trials} total</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-[11px] font-mono">
                  <thead className="text-text-muted text-[10px] uppercase border-b border-border-dark">
                    <tr>
                      <th className="py-1.5 px-2">#</th>
                      <th className="py-1.5 px-2">Rule</th>
                      <th className="py-1.5 px-2">Holdout ROI</th>
                      <th className="py-1.5 px-2">Verdict</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-dark/40">
                    {trials.recent.slice(0, 5).map(t => (
                      <tr key={t.id}>
                        <td className="py-2 px-2 text-text-muted">{t.id}</td>
                        <td className="py-2 px-2 text-text-primary truncate max-w-[200px]">{t.rule}</td>
                        <td className={`py-2 px-2 font-bold ${t.holdout_roi >= 0 ? "text-lemon" : "text-coral"}`}>
                          {t.holdout_roi > 0 ? "+" : ""}{t.holdout_roi?.toFixed(2)}%
                        </td>
                        <td className="py-2 px-2 text-text-muted">{t.verdict}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
