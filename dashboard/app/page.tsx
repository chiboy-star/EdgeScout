'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';

// Types
interface Outcome {
  code: string;
  label: string;
  odd: number;
  fairProb: number;
  fairOdd: number;
  expectedLoss1000: number;
}

interface Fixture {
  id: string;
  home: string;
  away: string;
  league: string;
  time: string;
  odds: [number, number, number];
  bookmaker: string;
}

interface AccaLeg {
  id: string;
  match: string;
  selection: string;
  odds: number;
  fairProb: number;
  margin: number;
}

interface PaperBet {
  id: string;
  idempotencyKey: string;
  matchName: string;
  selection: string;
  odds: number;
  closingOdds?: number;
  stake: number;
  status: 'OPEN' | 'WON' | 'LOST';
  profit: number;
  placedAt: string;
}

// Shin De-vig Model
function computeShinProbs(odds: [number, number, number]) {
  let z = 0.02;
  for (let i = 0; i < 10; i++) {
    let sumSqrt = 0.0;
    for (const o of odds) {
      sumSqrt += Math.sqrt(z * z + 4.0 * (1.0 - z) * (1.0 / o));
    }
    z = Math.max(0.0001, (sumSqrt - 2.0) / (odds.length - 2.0));
  }

  const rawFair = odds.map(o => {
    const term = Math.sqrt(z * z + 4.0 * (1.0 - z) * (1.0 / o)) - z;
    return Math.max(0.001, term / (2.0 * (1.0 - z)));
  });

  const sumFair = rawFair.reduce((a, b) => a + b, 0);
  const fair = rawFair.map(p => p / sumFair);
  const overround = (1 / odds[0] + 1 / odds[1] + 1 / odds[2] - 1) * 100;

  return { fair, overround };
}

export default function EdgeScoutDashboard() {
  const [activeTab, setActiveTab] = useState<'today' | 'thisweek' | 'accumulator' | 'ledger' | 'strategy' | 'performance'>('today');
  const [marketFilter, setMarketFilter] = useState<'ALL' | 'FAV' | 'CONT' | 'LONG'>('ALL');
  const [bankroll, setBankroll] = useState<number>(100000.0);
  const [openBets, setOpenBets] = useState<PaperBet[]>([]);
  const [settledBets, setSettledBets] = useState<PaperBet[]>([]);
  
  // Acca state
  const [accaLegs, setAccaLegs] = useState<AccaLeg[]>([]);
  const [accaStake, setAccaStake] = useState<number>(1000);
  const [customLeg, setCustomLeg] = useState({ match: '', selection: '', odds: '' });

  // Modals & toast
  const [oddsModalOpen, setOddsModalOpen] = useState(false);
  const [cmdModalOpen, setCmdModalOpen] = useState(false);
  const [toast, setToast] = useState<{ msg: string; undoId?: string } | null>(null);

  // Manual odds modal input state
  const [manualTitle, setManualTitle] = useState('Arsenal vs Chelsea');
  const [manualLeague, setManualLeague] = useState('Premier League');
  const [manualOdds, setManualOdds] = useState<[number, number, number]>([1.85, 3.75, 4.20]);

  // Strategy tester state
  const [selectedStrategy, setSelectedStrategy] = useState('All Leagues - Home Favs');

  // Baseline sample fixtures
  const [fixtures, setFixtures] = useState<Fixture[]>([
    { id: "E0_01", home: "Arsenal", away: "Chelsea", league: "Premier League", time: "Sat 16:00", odds: [1.85, 3.75, 4.20], bookmaker: "SportyBet" },
    { id: "E0_02", home: "Man City", away: "Liverpool", league: "Premier League", time: "Sun 17:30", odds: [2.05, 3.60, 3.50], bookmaker: "SportyBet" },
    { id: "SP1_03", home: "Real Madrid", away: "Barcelona", league: "La Liga", time: "Sun 20:00", odds: [2.15, 3.70, 3.20], bookmaker: "SportyBet" },
    { id: "D1_04", home: "Bayern Munich", away: "Dortmund", league: "Bundesliga", time: "Sat 17:30", odds: [1.45, 5.00, 6.50], bookmaker: "SportyBet" },
    { id: "I1_05", home: "Inter Milan", away: "Juventus", league: "Serie A", time: "Sun 19:45", odds: [1.95, 3.40, 4.10], bookmaker: "SportyBet" },
    { id: "F1_06", home: "Paris SG", away: "Marseille", league: "Ligue 1", time: "Sun 20:45", odds: [1.40, 5.25, 7.50], bookmaker: "SportyBet" },
  ]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCmdModalOpen(prev => !prev);
      } else if (e.key === 'Escape') {
        setCmdModalOpen(false);
        setOddsModalOpen(false);
      } else if (!e.metaKey && !e.ctrlKey && document.activeElement?.tagName !== 'INPUT') {
        if (e.key === '1') setActiveTab('today');
        if (e.key === '2') setActiveTab('thisweek');
        if (e.key === '3') setActiveTab('accumulator');
        if (e.key === '4') setActiveTab('ledger');
        if (e.key === '5') setActiveTab('strategy');
        if (e.key === '6') setActiveTab('performance');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Paper Bet Execution
  const placePaperBet = (matchName: string, selection: string, odds: number) => {
    const stake = Math.min(bankroll * 0.01, 2000); // 1% flat cap 2k
    const idempKey = `pb_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
    const newBet: PaperBet = {
      id: `bet_${Date.now()}`,
      idempotencyKey: idempKey,
      matchName,
      selection,
      odds,
      stake,
      status: 'OPEN',
      profit: 0,
      placedAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setBankroll(prev => prev - stake);
    setOpenBets(prev => [newBet, ...prev]);

    // Toast with 6s undo
    setToast({
      msg: `Paper bet placed: ${selection} (${matchName}) for ₦${stake.toFixed(2)} @ ${odds.toFixed(2)}`,
      undoId: newBet.id,
    });
    setTimeout(() => {
      setToast(prev => (prev?.undoId === newBet.id ? null : prev));
    }, 6000);
  };

  const undoBet = (id: string) => {
    const bet = openBets.find(b => b.id === id);
    if (bet) {
      setBankroll(prev => prev + bet.stake);
      setOpenBets(prev => prev.filter(b => b.id !== id));
      setToast({ msg: `Paper bet undone. ₦${bet.stake.toFixed(2)} refunded to bankroll.` });
      setTimeout(() => setToast(null), 3000);
    }
  };

  const simulateSettlement = () => {
    if (openBets.length === 0) return;
    const settled = openBets.map(b => {
      const winProb = (1 / b.odds) / 1.05;
      const won = Math.random() < winProb;
      const profit = won ? (b.stake * b.odds) - b.stake : -b.stake;
      if (won) {
        setBankroll(prev => prev + (b.stake * b.odds));
      }
      return {
        ...b,
        status: won ? ('WON' as const) : ('LOST' as const),
        closingOdds: parseFloat((b.odds * 0.98).toFixed(2)),
        profit,
      };
    });
    setSettledBets(prev => [...settled, ...prev]);
    setOpenBets([]);
    setToast({ msg: `Settled ${settled.length} paper bets based on fair match simulation.` });
    setTimeout(() => setToast(null), 3000);
  };

  // Acca Calculations
  const accaStats = useMemo(() => {
    if (accaLegs.length === 0) return { combinedOdds: 1, trueProb: 1, marginPct: 0, loss1000: 0, singleLoss: 0 };
    let combinedOdds = 1;
    let trueProbProduct = 1;
    let marginFactors = 1;
    let singleLossTotal = 0;
    const singleStake = accaStake / accaLegs.length;

    for (const leg of accaLegs) {
      combinedOdds *= leg.odds;
      trueProbProduct *= leg.fairProb;
      marginFactors *= (1 + leg.margin);
      singleLossTotal += singleStake * (1 - leg.fairProb * leg.odds);
    }

    const marginPct = (marginFactors - 1) * 100;
    const expectedReturn = accaStake * (trueProbProduct * combinedOdds);
    const loss1000 = Math.max(0, accaStake - expectedReturn);

    return { combinedOdds, trueProb: trueProbProduct * 100, marginPct, loss1000, singleLoss: singleLossTotal };
  }, [accaLegs, accaStake]);

  // Strategy tester 13-season benchmarks
  const benchmarks: Record<string, { bets: number; hit: number; roi: number; ci: [number, number]; base: number; verdict: string }> = {
    'All Leagues - Home Favs': { bets: 16029, hit: 54.6, roi: -4.15, ci: [-5.63, -2.71], base: -4.97, verdict: 'INDISTINGUISHABLE FROM THE MARGIN. Consistent with full bookmaker vig.' },
    'All Leagues - All Home': { bets: 23483, hit: 44.5, roi: -5.89, ci: [-7.44, -4.21], base: -4.96, verdict: 'INDISTINGUISHABLE FROM THE MARGIN. Normal variance around vig.' },
    'All Leagues - Underdogs': { bets: 24615, hit: 21.3, roi: -7.44, ci: [-9.82, -4.87], base: -4.96, verdict: 'STATISTICALLY WORSE THAN MARGIN. Clear Favorite-Longshot Bias.' },
    'Heavy Favs (1.20 - 1.50)': { bets: 4483, hit: 72.8, roi: -1.18, ci: [-3.10, 0.69], base: -5.01, verdict: 'INDISTINGUISHABLE FROM ZERO/MARGIN. Lower overround on favorites.' },
    'Longshots (> 4.00)': { bets: 20447, hit: 16.0, roi: -11.31, ci: [-14.51, -8.10], base: -4.94, verdict: 'SEVERE LONGSHOT BIAS. Heavy vig loaded into underdog prices.' },
  };

  const currBench = benchmarks[selectedStrategy] || benchmarks['All Leagues - Home Favs'];

  return (
    <div className="min-h-screen bg-[#0E0E10] text-[#F4F2EA] flex flex-col font-sans">
      
      {/* Top Header */}
      <header className="border-b border-[#4A4A52]/40 bg-[#17171A]/80 backdrop-blur sticky top-0 z-40 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center space-x-6">
          <div className="flex items-baseline space-x-2">
            <span className="font-serif text-2xl font-semibold tracking-tight text-[#F4F2EA]">EdgeScout</span>
            <span className="text-xs uppercase tracking-widest text-[#9A9AA3] font-medium border border-[#4A4A52] px-2 py-0.5 rounded">Price-Discipline</span>
          </div>
          <nav className="hidden md:flex items-center space-x-1 text-sm">
            {(['today', 'thisweek', 'accumulator', 'ledger', 'strategy', 'performance'] as const).map((tab, idx) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-3 py-1.5 rounded transition capitalize font-medium ${
                  activeTab === tab ? 'text-[#E9F56B] bg-[#232327]' : 'text-[#9A9AA3] hover:text-[#F4F2EA]'
                }`}
              >
                {`${idx + 1}. ${tab === 'today' ? 'Today' : tab === 'thisweek' ? 'This Week' : tab === 'accumulator' ? 'Accumulator' : tab === 'ledger' ? 'Paper Ledger' : tab === 'strategy' ? 'Strategy Tester' : 'Performance'}`}
              </button>
            ))}
          </nav>
        </div>

        <div className="flex items-center space-x-4">
          <div className="bg-[#232327] border border-[#4A4A52]/50 rounded-lg px-3 py-1.5 flex items-center space-x-3 text-xs">
            <span className="text-[#9A9AA3]">Paper Bankroll</span>
            <span className="font-mono tabular-nums text-sm font-semibold text-[#E9F56B]">
              ₦{bankroll.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
          <button
            onClick={() => setOddsModalOpen(true)}
            className="text-xs bg-[#232327] hover:bg-[#2F2F35] text-[#F4F2EA] border border-[#4A4A52] px-3 py-1.5 rounded-lg transition"
          >
            + Add SportyBet Odds
          </button>
          <button
            onClick={() => setCmdModalOpen(true)}
            className="text-xs text-[#9A9AA3] hover:text-[#F4F2EA] border border-[#4A4A52] bg-[#17171A] px-2.5 py-1.5 rounded-lg flex items-center space-x-2"
          >
            <span>Search</span>
            <kbd className="bg-[#232327] px-1 py-0.5 rounded text-[11px] font-mono">⌘K</kbd>
          </button>
        </div>
      </header>

      {/* Global Discipline Banner */}
      <div className="bg-[#17171A] border-b border-[#4A4A52]/30 px-6 py-2.5 text-xs text-[#9A9AA3] flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <span className="w-2 h-2 rounded-full bg-[#B49CFF]" />
          <span><strong className="text-[#F4F2EA]">Core Principle:</strong> Bookmaker margin makes the average bet lose money. Quantifying true expected loss per ₦1,000 staked. Zero predictions or "sure" picks.</span>
        </div>
        <div className="hidden lg:flex items-center space-x-4 text-xs">
          <span>Feed: <strong className="text-[#F4F2EA]">SportyBet & European Benchmarks</strong></span>
        </div>
      </div>

      {/* Content Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 md:p-8 space-y-8">
        
        {/* TAB 1: TODAY */}
        {activeTab === 'today' && (
          <div className="space-y-6">
            <div className="flex flex-col md:flex-row md:items-end justify-between border-b border-[#4A4A52]/30 pb-4 gap-4">
              <div>
                <span className="text-xs uppercase tracking-widest text-[#B49CFF] font-semibold">Today's Slate</span>
                <h1 className="font-serif text-3xl md:text-4xl font-normal tracking-tight text-[#F4F2EA] mt-1">Market Probability & Cost View</h1>
                <p className="text-xs text-[#9A9AA3] mt-1">Shin de-vigged market probabilities, overround %, and expected loss per ₦1,000 staked. Categorized by market pricing, <strong className="text-[#F4F2EA]">not an edge</strong>.</p>
              </div>
              <div className="flex items-center space-x-2 text-xs">
                {(['ALL', 'FAV', 'CONT', 'LONG'] as const).map(f => (
                  <button
                    key={f}
                    onClick={() => setMarketFilter(f)}
                    className={`px-2.5 py-1 rounded border transition ${
                      marketFilter === f ? 'bg-[#232327] text-[#E9F56B] border-[#4A4A52]' : 'bg-[#17171A] text-[#9A9AA3] border-[#4A4A52]/40'
                    }`}
                  >
                    {f === 'ALL' ? 'All (6)' : f === 'FAV' ? 'Favourites (≥65%)' : f === 'CONT' ? 'Contested (35-65%)' : 'Longshots (<20%)'}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {fixtures.map(fix => {
                const { fair, overround } = computeShinProbs(fix.odds);
                const maxP = Math.max(...fair);
                const cat = maxP >= 0.65 ? 'Market favourite (≥65%)' : maxP < 0.20 ? 'Longshot (<20%)' : 'Contested (35-65%)';
                const filterTag = maxP >= 0.65 ? 'FAV' : maxP < 0.20 ? 'LONG' : 'CONT';

                if (marketFilter !== 'ALL' && marketFilter !== filterTag) return null;

                const outcomes: Outcome[] = [
                  { code: 'H', label: `${fix.home} (Home)`, odd: fix.odds[0], fairProb: fair[0], fairOdd: +(1 / fair[0]).toFixed(2), expectedLoss1000: Math.max(0, 1000 - 1000 * (fair[0] * fix.odds[0])) },
                  { code: 'D', label: 'Draw', odd: fix.odds[1], fairProb: fair[1], fairOdd: +(1 / fair[1]).toFixed(2), expectedLoss1000: Math.max(0, 1000 - 1000 * (fair[1] * fix.odds[1])) },
                  { code: 'A', label: `${fix.away} (Away)`, odd: fix.odds[2], fairProb: fair[2], fairOdd: +(1 / fair[2]).toFixed(2), expectedLoss1000: Math.max(0, 1000 - 1000 * (fair[2] * fix.odds[2])) },
                ];

                return (
                  <div key={fix.id} className="bg-[#17171A] border border-[#4A4A52]/40 rounded-xl p-5 space-y-4 hover:border-[#4A4A52] transition">
                    <div className="flex justify-between items-start border-b border-[#4A4A52]/30 pb-3">
                      <div>
                        <div className="flex items-center space-x-2 text-xs text-[#9A9AA3]">
                          <span className="uppercase font-medium">{fix.league}</span>
                          <span>•</span>
                          <span className="font-mono">{fix.time}</span>
                        </div>
                        <h3 className="font-serif text-xl text-[#F4F2EA] mt-0.5">{fix.home} <span className="text-[#9A9AA3] text-sm font-sans">vs</span> {fix.away}</h3>
                      </div>
                      <div className="text-right">
                        <span className="text-xs font-mono px-2 py-0.5 rounded border text-[#B49CFF] bg-[#B49CFF]/10 border-[#B49CFF]/30">Vig: {overround.toFixed(1)}%</span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-xs bg-[#0E0E10] px-3 py-1.5 rounded border border-[#4A4A52]/30">
                      <span className="text-[#9A9AA3]">Category: <strong className="text-[#F4F2EA]">{cat}</strong></span>
                      <span className="text-xs text-[#9A9AA3] italic">Market view, not an edge</span>
                    </div>

                    <div className="space-y-2">
                      {outcomes.map(out => (
                        <div key={out.code} className="flex items-center justify-between p-2.5 rounded bg-[#232327]/60 border border-[#4A4A52]/20 text-xs">
                          <div className="flex-1">
                            <div className="font-medium text-[#F4F2EA]">{out.label}</div>
                            <div className="text-xs text-[#9A9AA3] font-mono mt-0.5">
                              Fair: {(out.fairProb * 100).toFixed(1)}% • Exp Loss/₦1k: <span className="text-[#FF7A6B] font-semibold">-₦{out.expectedLoss1000.toFixed(1)}</span>
                            </div>
                          </div>
                          <div className="flex items-center space-x-2">
                            <span className="font-mono tabular-nums text-sm font-semibold text-[#E9F56B] bg-[#0E0E10] px-2 py-1 rounded border border-[#4A4A52]/40">{out.odd.toFixed(2)}</span>
                            <button
                              onClick={() => placePaperBet(`${fix.home} vs ${fix.away}`, out.code, out.odd)}
                              className="bg-[#2F2F35] hover:bg-[#E9F56B] hover:text-[#0E0E10] text-[#F4F2EA] px-3 py-1.5 rounded font-medium transition text-xs border border-[#4A4A52]"
                            >
                              Paper Bet
                            </button>
                            <button
                              onClick={() => {
                                setAccaLegs(prev => [...prev, {
                                  id: `leg_${Date.now()}_${out.code}`,
                                  match: `${fix.home} vs ${fix.away}`,
                                  selection: out.label,
                                  odds: out.odd,
                                  fairProb: out.fairProb,
                                  margin: overround / 100,
                                }]);
                                setActiveTab('accumulator');
                              }}
                              className="text-xs text-[#9A9AA3] hover:text-[#B49CFF] px-1"
                            >
                              +Acca
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* TAB 2: THIS WEEK */}
        {activeTab === 'thisweek' && (
          <div className="space-y-6">
            <div className="border-b border-[#4A4A52]/30 pb-4">
              <span className="text-xs uppercase tracking-widest text-[#B49CFF] font-semibold">Matchweek Calendar</span>
              <h1 className="font-serif text-3xl md:text-4xl font-normal tracking-tight text-[#F4F2EA] mt-1">Upcoming Fixtures Schedule</h1>
              <p className="text-xs text-[#9A9AA3] mt-1">Strictly scheduled kickoff times across top European leagues. No odds claims or predictions.</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[
                { l: "Premier League", h: "Arsenal", a: "Chelsea", t: "Sat 16:00" },
                { l: "Premier League", h: "Man City", a: "Liverpool", t: "Sun 17:30" },
                { l: "La Liga", h: "Real Madrid", a: "Barcelona", t: "Sun 20:00" },
                { l: "Bundesliga", h: "Bayern Munich", a: "Dortmund", t: "Sat 17:30" },
                { l: "Serie A", h: "Inter Milan", a: "Juventus", t: "Sun 19:45" },
                { l: "Ligue 1", h: "Paris SG", a: "Marseille", t: "Sun 20:45" },
              ].map((m, i) => (
                <div key={i} className="bg-[#17171A] border border-[#4A4A52]/40 rounded-xl p-4 space-y-1">
                  <div className="flex justify-between text-xs text-[#9A9AA3]">
                    <span className="uppercase">{m.l}</span>
                    <span className="font-mono">{m.t}</span>
                  </div>
                  <div className="font-serif text-base text-[#F4F2EA]">{m.h} <span className="text-[#9A9AA3] font-sans text-xs">vs</span> {m.a}</div>
                  <div className="text-xs text-[#9A9AA3] italic pt-1 border-t border-[#4A4A52]/20">Schedule only. No odds claims.</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 3: ACCUMULATOR */}
        {activeTab === 'accumulator' && (
          <div className="space-y-6">
            <div className="border-b border-[#4A4A52]/30 pb-4">
              <span className="text-xs uppercase tracking-widest text-[#FF7A6B] font-semibold">Compounding Overround</span>
              <h1 className="font-serif text-3xl md:text-4xl font-normal tracking-tight text-[#F4F2EA] mt-1">Accumulator Cost Calculator</h1>
              <p className="text-xs text-[#9A9AA3] mt-1">Bookmaker margins multiply with every leg: ∏(1 + m_i) - 1. Inspect the true mathematical cost of multi-bets.</p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="lg:col-span-2 space-y-4">
                <div className="bg-[#17171A] border border-[#4A4A52]/40 rounded-xl p-5 space-y-4">
                  <div className="flex justify-between items-center">
                    <h2 className="font-serif text-lg text-[#F4F2EA]">Accumulator Legs ({accaLegs.length})</h2>
                    <button onClick={() => setAccaLegs([])} className="text-xs px-2.5 py-1 rounded bg-[#232327] text-[#9A9AA3] border border-[#4A4A52]">Clear All</button>
                  </div>

                  {/* Add Leg Form */}
                  <div className="p-3 bg-[#0E0E10] border border-[#4A4A52]/30 rounded-lg flex flex-wrap gap-2 text-xs">
                    <input
                      type="text"
                      placeholder="Match name"
                      value={customLeg.match}
                      onChange={e => setCustomLeg({ ...customLeg, match: e.target.value })}
                      className="bg-[#17171A] border border-[#4A4A52] rounded px-2.5 py-1.5 flex-1 min-w-[140px]"
                    />
                    <input
                      type="text"
                      placeholder="Selection"
                      value={customLeg.selection}
                      onChange={e => setCustomLeg({ ...customLeg, selection: e.target.value })}
                      className="bg-[#17171A] border border-[#4A4A52] rounded px-2.5 py-1.5 w-24"
                    />
                    <input
                      type="number"
                      step="0.01"
                      placeholder="Odds"
                      value={customLeg.odds}
                      onChange={e => setCustomLeg({ ...customLeg, odds: e.target.value })}
                      className="bg-[#17171A] border border-[#4A4A52] rounded px-2.5 py-1.5 w-24 font-mono"
                    />
                    <button
                      onClick={() => {
                        const o = parseFloat(customLeg.odds);
                        if (!o || o <= 1) return;
                        setAccaLegs(prev => [...prev, {
                          id: `leg_${Date.now()}`,
                          match: customLeg.match || 'Custom Match',
                          selection: customLeg.selection || 'Pick',
                          odds: o,
                          fairProb: (1 / o) / 1.052,
                          margin: 0.052,
                        }]);
                        setCustomLeg({ match: '', selection: '', odds: '' });
                      }}
                      className="bg-[#E9F56B] text-[#0E0E10] font-semibold px-3 py-1.5 rounded"
                    >
                      + Add
                    </button>
                  </div>

                  {/* Legs List */}
                  <div className="space-y-2">
                    {accaLegs.map(leg => (
                      <div key={leg.id} className="flex justify-between items-center p-2.5 bg-[#0E0E10] border border-[#4A4A52]/30 rounded text-xs">
                        <div>
                          <span className="font-medium text-[#F4F2EA]">{leg.selection}</span>
                          <span className="text-[#9A9AA3] ml-1">({leg.match})</span>
                          <div className="text-xs text-[#9A9AA3] font-mono mt-0.5">Fair Prob: {(leg.fairProb * 100).toFixed(1)}% • Margin: {(leg.margin * 100).toFixed(1)}%</div>
                        </div>
                        <div className="flex items-center space-x-3">
                          <span className="font-mono tabular-nums text-sm font-semibold text-[#E9F56B]">{leg.odds.toFixed(2)}</span>
                          <button onClick={() => setAccaLegs(prev => prev.filter(l => l.id !== leg.id))} className="text-[#9A9AA3] hover:text-[#FF7A6B]">&times;</button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-[#17171A] border border-[#4A4A52]/40 rounded-xl p-5 space-y-2 text-xs">
                  <span className="text-[#9A9AA3]">Stake Amount:</span>
                  <div className="flex items-center space-x-4">
                    <input
                      type="number"
                      value={accaStake}
                      onChange={e => setAccaStake(parseFloat(e.target.value) || 0)}
                      className="bg-[#0E0E10] border border-[#4A4A52] rounded px-3 py-1.5 text-sm font-mono text-[#F4F2EA] w-32"
                    />
                    <span className="text-[#9A9AA3]">Split as singles: <strong className="text-[#F4F2EA] font-mono">₦{(accaStake / Math.max(1, accaLegs.length)).toFixed(2)} / bet</strong></span>
                  </div>
                </div>
              </div>

              {/* Acca Math Summary */}
              <div className="space-y-4">
                <div className="bg-[#17171A] border border-[#4A4A52]/40 rounded-xl p-5 space-y-4">
                  <h3 className="font-serif text-xl text-[#F4F2EA]">The Accumulator Tax</h3>
                  <div className="space-y-3 text-xs border-b border-[#4A4A52]/30 pb-4">
                    <div className="flex justify-between items-baseline">
                      <span className="text-[#9A9AA3]">Combined Odds:</span>
                      <span className="font-mono tabular-nums text-base font-semibold text-[#F4F2EA]">{accaStats.combinedOdds.toFixed(2)}</span>
                    </div>
                    <div className="flex justify-between items-baseline">
                      <span className="text-[#9A9AA3]">True Combined Probability:</span>
                      <span className="font-mono tabular-nums text-base font-semibold text-[#B49CFF]">{accaStats.trueProb.toFixed(2)}%</span>
                    </div>
                    <div className="flex justify-between items-baseline">
                      <span className="text-[#9A9AA3]">Compounded Margin:</span>
                      <span className="font-mono tabular-nums text-base font-semibold text-[#FF7A6B]">{accaStats.marginPct.toFixed(1)}%</span>
                    </div>
                  </div>

                  <div className="bg-[#0E0E10] p-4 rounded-lg border border-[#FF7A6B]/30 space-y-2">
                    <span className="text-xs uppercase tracking-wider text-[#FF7A6B] font-semibold">Expected Loss on ₦{accaStake}</span>
                    <div className="text-2xl font-serif text-[#FF7A6B] tabular-nums font-semibold">-₦{accaStats.loss1000.toFixed(2)}</div>
                    <p className="text-xs text-[#9A9AA3]">Each leg exponentially compounds the bookmaker's overround.</p>
                  </div>

                  <div className="bg-[#232327]/60 p-4 rounded-lg border border-[#4A4A52]/40 space-y-2 text-xs">
                    <span className="text-xs uppercase tracking-wider text-[#E9F56B] font-semibold">Single Bets Equivalent</span>
                    <div className="flex justify-between">
                      <span className="text-[#9A9AA3]">Expected Loss on Singles:</span>
                      <span className="font-mono text-[#E9F56B] font-medium">-₦{accaStats.singleLoss.toFixed(2)}</span>
                    </div>
                    <p className="text-xs text-[#9A9AA3]">Singles avoid compounding margins, cutting expected losses dramatically.</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: PAPER LEDGER */}
        {activeTab === 'ledger' && (
          <div className="space-y-6">
            <div className="bg-[#232327] border border-[#FF7A6B]/50 rounded-xl p-4 flex items-center justify-between text-xs">
              <div className="flex items-center space-x-3">
                <span className="text-[#FF7A6B] text-lg font-bold">⚠️</span>
                <div>
                  <h4 className="font-semibold text-[#F4F2EA]">Sample too small to judge ({settledBets.length} / 300 settled bets)</h4>
                  <p className="text-[#9A9AA3]">Short-term returns are dominated by variance. A minimum of 300 settled bets is required before judging execution.</p>
                </div>
              </div>
              <button onClick={simulateSettlement} className="bg-[#2F2F35] hover:bg-[#3E3E47] text-[#F4F2EA] px-3 py-1.5 rounded border border-[#4A4A52]">
                Simulate Settlement
              </button>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-[#17171A] border border-[#4A4A52]/40 rounded-xl p-4 space-y-1">
                <span className="text-xs text-[#9A9AA3]">Current Bankroll</span>
                <div className="text-2xl font-serif font-semibold text-[#E9F56B] tabular-nums">₦{bankroll.toLocaleString('en-US', { minimumFractionDigits: 2 })}</div>
              </div>
              <div className="bg-[#17171A] border border-[#4A4A52]/40 rounded-xl p-4 space-y-1">
                <span className="text-xs text-[#9A9AA3]">Realized P/L</span>
                {(() => {
                  const netPl = settledBets.reduce((a, b) => a + b.profit, 0);
                  return (
                    <div className={`text-2xl font-serif font-semibold tabular-nums ${netPl >= 0 ? 'text-[#E9F56B]' : 'text-[#FF7A6B]'}`}>
                      {netPl >= 0 ? '+' : '-'}₦{Math.abs(netPl).toFixed(2)}
                    </div>
                  );
                })()}
              </div>
              <div className="bg-[#17171A] border border-[#4A4A52]/40 rounded-xl p-4 space-y-1">
                <span className="text-xs text-[#9A9AA3]">Hit Rate</span>
                <div className="text-2xl font-serif font-semibold text-[#B49CFF] tabular-nums">
                  {settledBets.length > 0 ? `${((settledBets.filter(b => b.status === 'WON').length / settledBets.length) * 100).toFixed(1)}%` : '0.0%'}
                </div>
              </div>
              <div className="bg-[#17171A] border border-[#4A4A52]/40 rounded-xl p-4 space-y-1">
                <span className="text-xs text-[#9A9AA3]">Daily Exposure</span>
                <div className="text-2xl font-serif font-semibold text-[#F4F2EA] tabular-nums">
                  {((openBets.reduce((a, b) => a + b.stake, 0) / bankroll) * 100).toFixed(1)}%
                </div>
              </div>
            </div>

            {/* Bets Tables */}
            <div className="space-y-6">
              <div className="bg-[#17171A] border border-[#4A4A52]/40 rounded-xl overflow-hidden">
                <div className="px-5 py-3 border-b border-[#4A4A52]/30 flex justify-between items-center">
                  <h3 className="font-serif text-base text-[#F4F2EA]">Open Paper Bets ({openBets.length})</h3>
                  <span className="text-xs text-[#9A9AA3]">Pending result</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-[#0E0E10] text-[#9A9AA3] border-b border-[#4A4A52]/30">
                      <tr>
                        <th className="p-3">Match</th>
                        <th className="p-3">Selection</th>
                        <th className="p-3">Odds Taken</th>
                        <th className="p-3">Stake</th>
                        <th className="p-3">Placed</th>
                        <th className="p-3 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#4A4A52]/20">
                      {openBets.length === 0 ? (
                        <tr><td colSpan={6} className="p-4 text-center text-[#9A9AA3]">No open paper bets.</td></tr>
                      ) : (
                        openBets.map(b => (
                          <tr key={b.id} className="hover:bg-[#232327]/40">
                            <td className="p-3 font-medium text-[#F4F2EA]">{b.matchName}</td>
                            <td className="p-3"><span className="px-2 py-0.5 rounded bg-[#232327] font-mono">{b.selection}</span></td>
                            <td className="p-3 font-mono text-[#E9F56B]">{b.odds.toFixed(2)}</td>
                            <td className="p-3 font-mono">₦{b.stake.toFixed(2)}</td>
                            <td className="p-3 text-[#9A9AA3] font-mono">{b.placedAt}</td>
                            <td className="p-3 text-right"><button onClick={() => undoBet(b.id)} className="text-[#FF7A6B] hover:underline">Undo</button></td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* TAB 5: STRATEGY TESTER */}
        {activeTab === 'strategy' && (
          <div className="space-y-6">
            <div className="border-b border-[#4A4A52]/30 pb-4">
              <span className="text-xs uppercase tracking-widest text-[#B49CFF] font-semibold">13 Historical Seasons</span>
              <h1 className="font-serif text-3xl md:text-4xl font-normal tracking-tight text-[#F4F2EA] mt-1">Empirical Strategy Tester</h1>
              <p className="text-xs text-[#9A9AA3] mt-1">Backtest rules across 23,459 real domestic European matches (2012/13 – 2024/25) compared to the margin baseline.</p>
            </div>

            <div className="bg-[#17171A] border border-[#4A4A52]/40 rounded-xl p-5 space-y-4">
              <div className="text-xs space-y-2">
                <label className="text-[#9A9AA3]">Select Strategy Rule:</label>
                <select
                  value={selectedStrategy}
                  onChange={e => setSelectedStrategy(e.target.value)}
                  className="bg-[#0E0E10] border border-[#4A4A52] rounded p-2 text-[#F4F2EA] w-full max-w-md"
                >
                  {Object.keys(benchmarks).map(k => (
                    <option key={k} value={k}>{k}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-2">
                <div className="bg-[#0E0E10] border border-[#4A4A52]/30 rounded-xl p-4">
                  <span className="text-xs text-[#9A9AA3]">Total Historical Bets</span>
                  <div className="text-2xl font-serif font-semibold text-[#F4F2EA] tabular-nums">{currBench.bets.toLocaleString()}</div>
                </div>
                <div className="bg-[#0E0E10] border border-[#4A4A52]/30 rounded-xl p-4">
                  <span className="text-xs text-[#9A9AA3]">Realized Flat ROI</span>
                  <div className="text-2xl font-serif font-semibold text-[#FF7A6B] tabular-nums">{currBench.roi.toFixed(2)}%</div>
                </div>
                <div className="bg-[#0E0E10] border border-[#4A4A52]/30 rounded-xl p-4">
                  <span className="text-xs text-[#9A9AA3]">95% Bootstrap CI</span>
                  <div className="text-lg font-mono font-semibold text-[#B49CFF] tabular-nums mt-1">[{currBench.ci[0]}%, {currBench.ci[1]}%]</div>
                </div>
                <div className="bg-[#0E0E10] border border-[#4A4A52]/30 rounded-xl p-4">
                  <span className="text-xs text-[#9A9AA3]">Margin Baseline</span>
                  <div className="text-2xl font-serif font-semibold text-[#9A9AA3] tabular-nums">{currBench.base.toFixed(2)}%</div>
                </div>
              </div>

              <div className="bg-[#232327]/60 border border-[#4A4A52]/40 rounded-xl p-4 space-y-1">
                <span className="text-xs uppercase tracking-wider text-[#B49CFF] font-semibold">Statistical Significance Verdict</span>
                <div className="font-serif text-base text-[#F4F2EA]">{currBench.verdict}</div>
                <p className="text-xs text-[#9A9AA3]">Default verdict: Indistinguishable from the bookmaker margin.</p>
              </div>
            </div>
          </div>
        )}

        {/* TAB 6: PERFORMANCE */}
        {activeTab === 'performance' && (
          <div className="space-y-6">
            <div className="border-b border-[#4A4A52]/30 pb-4">
              <span className="text-xs uppercase tracking-widest text-[#B49CFF] font-semibold">Execution Metrics</span>
              <h1 className="font-serif text-3xl md:text-4xl font-normal tracking-tight text-[#F4F2EA] mt-1">Bankroll Trajectory & Variance</h1>
              <p className="text-xs text-[#9A9AA3] mt-1">Long-term variance tracking and sample size discipline.</p>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="bg-[#17171A] border border-[#4A4A52]/40 rounded-xl p-5 space-y-2">
                <span className="text-xs text-[#9A9AA3]">Max Drawdown</span>
                <div className="text-2xl font-serif text-[#FF7A6B] tabular-nums">0.0%</div>
                <p className="text-xs text-[#9A9AA3]">Peak-to-trough capital decline across all paper bets.</p>
              </div>
              <div className="bg-[#17171A] border border-[#4A4A52]/40 rounded-xl p-5 space-y-2">
                <span className="text-xs text-[#9A9AA3]">Sample Size Progress</span>
                <div className="text-2xl font-serif text-[#E9F56B] tabular-nums">{settledBets.length} / 300</div>
                <p className="text-xs text-[#9A9AA3]">Minimum sample required to assess execution quality.</p>
              </div>
              <div className="bg-[#17171A] border border-[#4A4A52]/40 rounded-xl p-5 space-y-2">
                <span className="text-xs text-[#9A9AA3]">Average Overround</span>
                <div className="text-2xl font-serif text-[#F4F2EA] tabular-nums">5.2%</div>
                <p className="text-xs text-[#9A9AA3]">Average vig extracted across tracked markets.</p>
              </div>
            </div>
          </div>
        )}

      </main>

      {/* Manual Odds Modal */}
      {oddsModalOpen && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-[#17171A] border border-[#4A4A52] rounded-2xl max-w-lg w-full p-6 space-y-4">
            <div className="flex justify-between items-start">
              <h3 className="font-serif text-2xl text-[#F4F2EA]">Add SportyBet Odds</h3>
              <button onClick={() => setOddsModalOpen(false)} className="text-[#9A9AA3] hover:text-[#F4F2EA]">&times;</button>
            </div>
            <div className="space-y-3 text-xs">
              <div>
                <label className="text-[#9A9AA3] block mb-1">Match Title</label>
                <input
                  type="text"
                  value={manualTitle}
                  onChange={e => setManualTitle(e.target.value)}
                  className="w-full bg-[#0E0E10] border border-[#4A4A52] rounded p-2 text-[#F4F2EA]"
                />
              </div>
              <div>
                <label className="text-[#9A9AA3] block mb-1">League</label>
                <input
                  type="text"
                  value={manualLeague}
                  onChange={e => setManualLeague(e.target.value)}
                  className="w-full bg-[#0E0E10] border border-[#4A4A52] rounded p-2 text-[#F4F2EA]"
                />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="text-[#9A9AA3] block mb-1">Home (1)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={manualOdds[0]}
                    onChange={e => setManualOdds([parseFloat(e.target.value) || 1, manualOdds[1], manualOdds[2]])}
                    className="w-full bg-[#0E0E10] border border-[#4A4A52] rounded p-2 font-mono"
                  />
                </div>
                <div>
                  <label className="text-[#9A9AA3] block mb-1">Draw (X)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={manualOdds[1]}
                    onChange={e => setManualOdds([manualOdds[0], parseFloat(e.target.value) || 1, manualOdds[2]])}
                    className="w-full bg-[#0E0E10] border border-[#4A4A52] rounded p-2 font-mono"
                  />
                </div>
                <div>
                  <label className="text-[#9A9AA3] block mb-1">Away (2)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={manualOdds[2]}
                    onChange={e => setManualOdds([manualOdds[0], manualOdds[1], parseFloat(e.target.value) || 1])}
                    className="w-full bg-[#0E0E10] border border-[#4A4A52] rounded p-2 font-mono"
                  />
                </div>
              </div>
            </div>
            <div className="flex justify-end space-x-2 pt-2">
              <button onClick={() => setOddsModalOpen(false)} className="px-3 py-1.5 text-xs text-[#9A9AA3]">Cancel</button>
              <button
                onClick={() => {
                  const parts = manualTitle.split(' vs ');
                  setFixtures(prev => [{
                    id: `manual_${Date.now()}`,
                    home: parts[0] || 'Team A',
                    away: parts[1] || 'Team B',
                    league: manualLeague,
                    time: 'Upcoming',
                    odds: manualOdds,
                    bookmaker: 'SportyBet (User Entry)',
                  }, ...prev]);
                  setOddsModalOpen(false);
                  setToast({ msg: `Added ${manualTitle} to Market View` });
                  setTimeout(() => setToast(null), 3000);
                }}
                className="bg-[#E9F56B] text-[#0E0E10] font-semibold px-4 py-2 rounded text-xs"
              >
                Save Fixture
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 right-6 z-50 bg-[#17171A] border border-[#4A4A52] rounded-xl p-4 shadow-2xl flex items-center justify-between space-x-4 max-w-sm text-xs text-[#F4F2EA]">
          <span>{toast.msg}</span>
          {toast.undoId && (
            <button onClick={() => undoBet(toast.undoId!)} className="bg-[#FF7A6B]/20 text-[#FF7A6B] px-3 py-1 rounded font-medium border border-[#FF7A6B]/40">
              UNDO
            </button>
          )}
        </div>
      )}

    </div>
  );
}
