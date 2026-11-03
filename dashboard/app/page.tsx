"use client";

import React, { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { 
  api, 
  ShortlistResponse, 
  ShortlistCandidate, 
  LedgerSummary, 
  FixtureItem,
  DataHealthStats 
} from "../lib/api";
import { Navbar } from "../components/Navbar";
import { DataHealthStrip } from "../components/DataHealthStrip";
import { CommandMenu } from "../components/CommandMenu";
import { ShortlistTab } from "../components/ShortlistTab";
import { FixturesTab } from "../components/FixturesTab";
import { LedgerTab } from "../components/LedgerTab";
import { AccumulatorTab } from "../components/AccumulatorTab";
import { StrategyTesterTab } from "../components/StrategyTesterTab";
import { ManualOddsModal, ManualOddsPrefill } from "../components/ManualOddsModal";
import { AddCustomFixtureModal } from "../components/AddCustomFixtureModal";

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<string>("shortlist");
  const [cmdkOpen, setCmdkOpen] = useState(false);
  const [customOddsOpen, setCustomOddsOpen] = useState(false);
  const [addFixtureOpen, setAddFixtureOpen] = useState(false);
  const [shortlistTimeframe, setShortlistTimeframe] = useState<"today" | "week">("today");
  const [customOddsPrefill, setCustomOddsPrefill] = useState<ManualOddsPrefill | null>(null);

  const [shortlist, setShortlist] = useState<ShortlistResponse | null>(null);
  const [fixtures, setFixtures] = useState<FixtureItem[]>([]);
  const [ledger, setLedger] = useState<LedgerSummary | null>(null);
  const [dataHealth, setDataHealth] = useState<DataHealthStats | null>(null);

  const [loadingShortlist, setLoadingShortlist] = useState(false);
  const [loadingFixtures, setLoadingFixtures] = useState(false);
  const [loadingLedger, setLoadingLedger] = useState(false);
  const [loadingHealth, setLoadingHealth] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());

  // Load Data Health Strip
  const loadDataHealth = useCallback(async () => {
    setLoadingHealth(true);
    try {
      const stats = await api.getDataHealth();
      setDataHealth(stats);
      return stats;
    } catch (e) {
      console.error("Failed to load data health stats:", e);
      return null;
    } finally {
      setLoadingHealth(false);
    }
  }, []);

  // Load Shortlist
  const loadShortlist = useCallback(async (currentBankroll?: number, tf?: "today" | "week") => {
    setLoadingShortlist(true);
    const activeTf = tf || shortlistTimeframe;
    try {
      const data = await api.getShortlist(currentBankroll, activeTf);
      setShortlist(data);
      if (data.data_health) {
        setDataHealth(data.data_health);
      }
    } catch (e) {
      console.error("Failed to load shortlist:", e);
    } finally {
      setLoadingShortlist(false);
    }
  }, [shortlistTimeframe]);

  // Load Fixtures
  const loadFixtures = useCallback(async () => {
    setLoadingFixtures(true);
    try {
      const data = await api.getFixtures();
      setFixtures(data.fixtures || []);
    } catch (e) {
      console.error("Failed to load fixtures:", e);
    } finally {
      setLoadingFixtures(false);
    }
  }, []);

  // Load Ledger
  const loadLedger = useCallback(async () => {
    setLoadingLedger(true);
    try {
      const data = await api.getLedger();
      setLedger(data);
      return data;
    } catch (e) {
      console.error("Failed to load ledger:", e);
      return null;
    } finally {
      setLoadingLedger(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    const init = async () => {
      await loadDataHealth();
      const leg = await loadLedger();
      await loadShortlist(leg?.current_bankroll);
      await loadFixtures();
      setLastUpdated(new Date());
    };
    init();
  }, [loadDataHealth, loadLedger, loadShortlist, loadFixtures]);

  const handleRefresh = async () => {
    await loadDataHealth();
    const leg = await loadLedger();
    await loadShortlist(leg?.current_bankroll);
    await loadFixtures();
    setLastUpdated(new Date());
    toast.info("Market data refreshed");
  };

  // Re-download fixtures.csv
  const handleRefreshFixtures = async () => {
    try {
      const freshStats = await api.refreshFixtures();
      setDataHealth(freshStats);
      await loadFixtures();
      if (ledger) {
        await loadShortlist(ledger.current_bankroll);
      }
      toast.success("Fixtures feed re-downloaded & cache refreshed");
    } catch (err: any) {
      toast.error("Failed to re-download fixtures: " + (err.message || "Network error"));
    }
  };

  // Place bet with optimistic update & 6s undo toast
  const handlePlaceBet = async (candidate: ShortlistCandidate) => {
    const idempotencyKey = typeof crypto !== "undefined" && crypto.randomUUID 
      ? crypto.randomUUID() 
      : `idemp_${Date.now()}_${Math.random()}`;

    const stakeAmount = candidate.suggested_stake || 1000;

    // Optimistic Ledger Update
    if (ledger) {
      const tempBet = {
        id: idempotencyKey,
        idempotency_key: idempotencyKey,
        match_id: candidate.match_id,
        match_name: candidate.match_name,
        league_code: candidate.league_code,
        selection: candidate.selection,
        odds_taken: candidate.odds_taken,
        closing_odds: null,
        clv: null,
        stake: stakeAmount,
        stake_fraction: stakeAmount / ledger.current_bankroll,
        status: "OPEN" as const,
        settlement_type: null,
        profit_loss: 0,
        placed_at: new Date().toISOString(),
        settled_at: null,
      };

      setLedger({
        ...ledger,
        current_bankroll: Math.max(0, ledger.current_bankroll - stakeAmount),
        open_bets: ledger.open_bets + 1,
        total_bets: ledger.total_bets + 1,
        bets: [tempBet, ...(ledger.bets || [])],
      });
    }

    try {
      const res = await api.placeBet({
        idempotency_key: idempotencyKey,
        match_id: candidate.match_id,
        match_name: candidate.match_name,
        league_code: candidate.league_code,
        selection: candidate.selection,
        odds: candidate.odds_taken,
        stake: stakeAmount,
        kickoff_utc: candidate.kickoff_utc,
      });

      const placedBetId = res.bet_id || idempotencyKey;

      // Sonner Undo Toast (6 seconds window)
      toast.success(`Paper bet placed: ${candidate.selection_label} @ ${candidate.odds_taken}`, {
        duration: 6000,
        action: {
          label: "Undo (6s)",
          onClick: async () => {
            try {
              await api.undoBet(placedBetId);
              toast.info("Bet undone. Stake refunded to bankroll.");
              await loadLedger();
            } catch (err) {
              toast.error("Could not undo bet");
            }
          },
        },
      });

      await loadLedger();
    } catch (err: any) {
      toast.error(err.message || "Failed to place bet");
      await loadLedger();
    }
  };

  // Place custom odds bet
  const handlePlaceCustomBet = async (data: {
    match_id: string;
    match_name: string;
    selection: string;
    odds: number;
    stake: number;
    kickoff_utc?: string;
  }) => {
    const idempotencyKey = typeof crypto !== "undefined" && crypto.randomUUID 
      ? crypto.randomUUID() 
      : `custom_${Date.now()}_${Math.random()}`;

    try {
      const res = await api.placeBet({
        idempotency_key: idempotencyKey,
        match_id: data.match_id,
        match_name: data.match_name,
        league_code: "SPORTY",
        selection: data.selection,
        odds: data.odds,
        stake: data.stake,
        kickoff_utc: data.kickoff_utc,
      });

      const placedBetId = res.bet_id || idempotencyKey;

      toast.success(`Custom SportyBet bet placed: ${data.match_name} @ ${data.odds}`, {
        duration: 6000,
        action: {
          label: "Undo (6s)",
          onClick: async () => {
            try {
              await api.undoBet(placedBetId);
              toast.info("Custom bet undone. Stake refunded.");
              await loadLedger();
            } catch (e) {
              toast.error("Could not undo bet");
            }
          },
        },
      });

      await loadLedger();
    } catch (err: any) {
      toast.error(err.message || "Failed to place custom bet");
    }
  };

  // Auto settle
  const handleAutoSettle = async () => {
    try {
      const res = await api.autoSettle();
      const updated = res.settled_bets_count || 0;
      toast.success(
        res.is_demo_feed 
          ? `Settled ${updated} bets from demo results feed`
          : `Settled ${updated} bets from live football-data.org feed`
      );
      await loadLedger();
    } catch (err: any) {
      toast.error("Auto settle failed: " + err.message);
    }
  };

  // Manual settle
  const handleManualSettle = async (betId: string, outcome: string, closingOdds?: number) => {
    try {
      await api.manualSettle({
        bet_id: betId,
        outcome,
        closing_odds: closingOdds,
      });
      toast.success(`Bet settled as ${outcome}${closingOdds ? ` (CLV recorded)` : ""}`);
      await loadLedger();
    } catch (err: any) {
      toast.error("Manual settlement failed: " + err.message);
    }
  };

  // Reset bankroll
  const handleResetBankroll = async () => {
    if (confirm("Are you sure you want to reset your paper bankroll to ₦100,000? All bet history will be cleared.")) {
      try {
        await api.resetBankroll(100000);
        toast.info("Bankroll reset to ₦100,000.00");
        await loadLedger();
      } catch (err: any) {
        toast.error("Failed to reset bankroll");
      }
    }
  };

  const openCustomOddsModal = (prefillData?: any) => {
    if (typeof prefillData === "string") {
      setCustomOddsPrefill({ match_name: prefillData });
    } else if (prefillData && typeof prefillData === "object") {
      setCustomOddsPrefill(prefillData);
    } else {
      setCustomOddsPrefill({ match_name: "Arsenal vs Chelsea" });
    }
    setCustomOddsOpen(true);
  };

  // Exposure calculation
  const openStake = (ledger?.bets || [])
    .filter(b => b.status === "OPEN")
    .reduce((sum, b) => sum + b.stake, 0);
  const currentBankroll = ledger?.current_bankroll || 100000;
  const dailyExposurePct = currentBankroll > 0 ? (openStake / currentBankroll) * 100 : 0;

  return (
    <div className="min-h-screen bg-bg-950 text-text-primary flex flex-col">
      {/* Top Navigation */}
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        bankroll={currentBankroll}
        openBetsCount={ledger?.open_bets || 0}
        dailyExposurePct={dailyExposurePct}
        lastUpdated={lastUpdated}
        onRefresh={handleRefresh}
        onOpenCmdk={() => setCmdkOpen(true)}
      />

      {/* Data Health Strip (DB Latest Date, Fixtures Freshness, Next Kickoff in WAT, Upcoming Count) */}
      <DataHealthStrip
        stats={dataHealth}
        loading={loadingHealth}
        onRefreshFixtures={handleRefreshFixtures}
        onOpenAddCustomFixture={() => setAddFixtureOpen(true)}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === "shortlist" && (
          <ShortlistTab
            shortlist={shortlist}
            loading={loadingShortlist}
            timeframe={shortlistTimeframe}
            onTimeframeChange={(tf) => {
              setShortlistTimeframe(tf);
              loadShortlist(ledger?.current_bankroll, tf);
            }}
            onPlaceBet={handlePlaceBet}
            onOpenCustomOdds={openCustomOddsModal}
            onOpenAddCustomFixture={() => setAddFixtureOpen(true)}
          />
        )}

        {activeTab === "fixtures" && (
          <FixturesTab
            fixtures={fixtures}
            loading={loadingFixtures}
            onOpenCustomOdds={openCustomOddsModal}
            onOpenAddCustomFixture={() => setAddFixtureOpen(true)}
            onRefresh={handleRefresh}
          />
        )}

        {activeTab === "ledger" && (
          <LedgerTab
            ledger={ledger}
            loading={loadingLedger}
            onAutoSettle={handleAutoSettle}
            onManualSettle={handleManualSettle}
            onResetBankroll={handleResetBankroll}
          />
        )}

        {activeTab === "accumulator" && (
          <AccumulatorTab />
        )}

        {activeTab === "strategy" && (
          <StrategyTesterTab />
        )}
      </main>

      {/* Command Menu Modal */}
      <CommandMenu
        open={cmdkOpen}
        setOpen={setCmdkOpen}
        setActiveTab={setActiveTab}
        onAutoSettle={handleAutoSettle}
        onResetBankroll={handleResetBankroll}
        onOpenCustomOdds={() => openCustomOddsModal()}
      />

      {/* Manual Odds Entry Modal */}
      <ManualOddsModal
        open={customOddsOpen}
        onClose={() => setCustomOddsOpen(false)}
        prefill={customOddsPrefill}
        onPlaceBet={handlePlaceCustomBet}
      />

      {/* Add Custom Fixture Modal */}
      <AddCustomFixtureModal
        open={addFixtureOpen}
        onClose={() => setAddFixtureOpen(false)}
        onSuccess={async () => {
          await loadDataHealth();
          await loadFixtures();
          await loadShortlist(ledger?.current_bankroll);
        }}
      />

      {/* Footer */}
      <footer className="border-t border-border-dark py-6 text-center text-xs text-text-muted">
        <div className="max-w-7xl mx-auto px-4 flex flex-col md:flex-row items-center justify-between gap-2">
          <span>EdgeScout v4.0.0 — Price-Discipline & Bet-Tracking Engine</span>
          <span className="italic font-mono text-[11px]">
            Lowest-cost picks, not a prediction of profit. Margin ensures negative average return.
          </span>
        </div>
      </footer>
    </div>
  );
}
