"use client";

import React, { useState } from "react";
import { X, Calendar, PlusCircle, AlertCircle, ShieldCheck } from "lucide-react";
import { api } from "../lib/api";
import { toast } from "sonner";

interface AddCustomFixtureModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function AddCustomFixtureModal({
  open,
  onClose,
  onSuccess,
}: AddCustomFixtureModalProps) {
  const [matchName, setMatchName] = useState("");
  const [league, setLeague] = useState("UEFA Champions League");
  const [kickoffDate, setKickoffDate] = useState(() => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    return tomorrow.toISOString().split("T")[0];
  });
  const [kickoffTime, setKickoffTime] = useState("20:00");
  const [homeOdds, setHomeOdds] = useState("2.10");
  const [drawOdds, setDrawOdds] = useState("3.40");
  const [awayOdds, setAwayOdds] = useState("3.50");
  const [loading, setLoading] = useState(false);

  if (!open) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const h = parseFloat(homeOdds) || 0;
    const d = parseFloat(drawOdds) || 0;
    const a = parseFloat(awayOdds) || 0;

    if (!matchName.trim()) {
      toast.error("Please enter a valid match name (e.g. Arsenal vs Chelsea)");
      return;
    }
    if (h <= 1.0 || d <= 1.0 || a <= 1.0) {
      toast.error("All 1X2 decimal odds must be greater than 1.00");
      return;
    }

    // Convert date + time to UTC
    let kickoffIso = "";
    try {
      const dtLocal = new Date(`${kickoffDate}T${kickoffTime}:00`);
      kickoffIso = dtLocal.toISOString();
    } catch {
      toast.error("Invalid date or time entered");
      return;
    }

    setLoading(true);
    try {
      await api.addCustomFixture({
        match_name: matchName.trim(),
        league: league.trim(),
        kickoff_utc: kickoffIso,
        home_odds: h,
        draw_odds: d,
        away_odds: a,
      });
      toast.success(`Custom fixture added: ${matchName}`);
      onSuccess();
      onClose();
    } catch (err: any) {
      toast.error(err.message || "Failed to add custom fixture");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-bg-950/80 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="w-full max-w-md bg-bg-900 border border-border-subdued rounded-2xl shadow-2xl p-5 space-y-4">
        {/* Modal Header */}
        <div className="flex items-center justify-between pb-3 border-b border-border-dark">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-lemon/10 text-lemon">
              <Calendar className="w-4 h-4" />
            </div>
            <div>
              <h3 className="font-display font-bold text-text-primary text-sm">
                Add Custom Fixture & Odds
              </h3>
              <p className="text-[11px] text-text-muted">
                Enter any upcoming match to track in EdgeScout with real margin analysis
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

        {/* Modal Form */}
        <form onSubmit={handleSubmit} className="space-y-3.5 text-xs">
          <div>
            <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">
              Match / Event Name
            </label>
            <input
              type="text"
              value={matchName}
              onChange={(e) => setMatchName(e.target.value)}
              placeholder="e.g. Manchester United vs Roma"
              required
              className="w-full bg-bg-950 border border-border-dark rounded-lg px-3 py-2 text-text-primary focus:outline-none focus:border-lavender"
            />
          </div>

          <div>
            <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">
              Competition / League
            </label>
            <select
              value={league}
              onChange={(e) => setLeague(e.target.value)}
              className="w-full bg-bg-950 border border-border-dark rounded-lg px-2.5 py-2 text-text-primary focus:outline-none focus:border-lavender"
            >
              <option value="UEFA Champions League">UEFA Champions League</option>
              <option value="UEFA Europa League">UEFA Europa League</option>
              <option value="Premier League">Premier League</option>
              <option value="Championship">Championship</option>
              <option value="La Liga">La Liga</option>
              <option value="Serie A">Serie A</option>
              <option value="Bundesliga">Bundesliga</option>
              <option value="Ligue 1">Ligue 1</option>
              <option value="Other Competition">Other Competition</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">
                Kickoff Date
              </label>
              <input
                type="date"
                value={kickoffDate}
                onChange={(e) => setKickoffDate(e.target.value)}
                required
                className="w-full bg-bg-950 border border-border-dark rounded-lg px-2.5 py-1.5 text-text-primary focus:outline-none focus:border-lavender"
              />
            </div>
            <div>
              <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">
                Kickoff Time (Local)
              </label>
              <input
                type="time"
                value={kickoffTime}
                onChange={(e) => setKickoffTime(e.target.value)}
                required
                className="w-full bg-bg-950 border border-border-dark rounded-lg px-2.5 py-1.5 text-text-primary focus:outline-none focus:border-lavender"
              />
            </div>
          </div>

          {/* 1X2 Decimal Odds */}
          <div>
            <label className="text-[10px] text-text-muted font-mono uppercase block mb-1">
              1X2 Decimal Odds (e.g. from SportyBet)
            </label>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <span className="text-[9px] text-text-muted block text-center mb-0.5">Home (1)</span>
                <input
                  type="number"
                  step="0.01"
                  min="1.01"
                  value={homeOdds}
                  onChange={(e) => setHomeOdds(e.target.value)}
                  required
                  className="w-full bg-bg-950 border border-border-dark rounded-lg px-2 py-1.5 font-mono text-center text-text-primary font-bold focus:outline-none focus:border-lavender"
                />
              </div>
              <div>
                <span className="text-[9px] text-text-muted block text-center mb-0.5">Draw (X)</span>
                <input
                  type="number"
                  step="0.01"
                  min="1.01"
                  value={drawOdds}
                  onChange={(e) => setDrawOdds(e.target.value)}
                  required
                  className="w-full bg-bg-950 border border-border-dark rounded-lg px-2 py-1.5 font-mono text-center text-text-primary font-bold focus:outline-none focus:border-lavender"
                />
              </div>
              <div>
                <span className="text-[9px] text-text-muted block text-center mb-0.5">Away (2)</span>
                <input
                  type="number"
                  step="0.01"
                  min="1.01"
                  value={awayOdds}
                  onChange={(e) => setAwayOdds(e.target.value)}
                  required
                  className="w-full bg-bg-950 border border-border-dark rounded-lg px-2 py-1.5 font-mono text-center text-text-primary font-bold focus:outline-none focus:border-lavender"
                />
              </div>
            </div>
          </div>

          {/* Real Data Provenance Note */}
          <div className="p-2.5 rounded-lg bg-bg-950 border border-border-dark text-[11px] text-text-muted flex items-start gap-1.5">
            <ShieldCheck className="w-3.5 h-3.5 text-lavender shrink-0 mt-0.5" />
            <span>
              This match will be stored with source <strong className="text-text-primary">"manual_entry"</strong> and will appear in Market View and Shortlists with margin metrics calculated.
            </span>
          </div>

          <div className="pt-2 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 bg-bg-800 text-text-muted hover:text-text-primary rounded-lg text-xs"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-1.5 bg-lavender hover:bg-lavender/90 text-bg-950 font-medium rounded-lg text-xs flex items-center gap-1.5 shadow-sm active:scale-95 disabled:opacity-50"
            >
              <PlusCircle className="w-3.5 h-3.5" />
              <span>{loading ? "Adding..." : "Add Fixture"}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
