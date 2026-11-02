"use client";

import React, { useEffect, useState } from "react";
import { 
  Sparkles, 
  Calendar, 
  BookOpen, 
  Layers, 
  FlaskConical, 
  TrendingUp, 
  RotateCcw, 
  Search,
  AlertTriangle,
  Clock
} from "lucide-react";

interface NavbarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  bankroll: number;
  openBetsCount: number;
  dailyExposurePct: number;
  lastUpdated: Date;
  onRefresh: () => void;
  onOpenCmdk: () => void;
}

export function Navbar({
  activeTab,
  setActiveTab,
  bankroll,
  openBetsCount,
  dailyExposurePct,
  lastUpdated,
  onRefresh,
  onOpenCmdk,
}: NavbarProps) {
  const [timeAgo, setTimeAgo] = useState("just now");

  useEffect(() => {
    const update = () => {
      const diffSec = Math.floor((Date.now() - lastUpdated.getTime()) / 1000);
      if (diffSec < 30) setTimeAgo("just now");
      else if (diffSec < 60) setTimeAgo(`${diffSec}s ago`);
      else setTimeAgo(`${Math.floor(diffSec / 60)}m ago`);
    };
    update();
    const interval = setInterval(update, 10000);
    return () => clearInterval(interval);
  }, [lastUpdated]);

  const navItems = [
    { id: "shortlist", label: "Today (Shortlist)", icon: Sparkles },
    { id: "fixtures", label: "This Week", icon: Calendar },
    { id: "ledger", label: "Paper Ledger", icon: BookOpen, badge: openBetsCount > 0 ? openBetsCount : null },
    { id: "accumulator", label: "Accumulator Cost", icon: Layers },
    { id: "strategy", label: "Strategy Tester", icon: FlaskConical },
  ];

  const exposureNearCap = dailyExposurePct >= 5.0;

  return (
    <header className="sticky top-0 z-30 bg-bg-950/90 backdrop-blur-md border-b border-border-dark py-3">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Logo and Tagline */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-lemon flex items-center justify-center font-bold text-bg-950 text-sm shadow-sm font-display">
              ES
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-display font-bold text-lg tracking-tight text-text-primary">
                  EdgeScout
                </span>
              </div>
              <p className="text-xs text-text-muted">
                Price Discipline & Paper-Trading Ledger
              </p>
            </div>
          </div>

          {/* Mobile Cmdk button */}
          <button
            onClick={onOpenCmdk}
            className="md:hidden p-2 rounded-lg bg-bg-900 border border-border-dark text-text-muted hover:text-text-primary"
            aria-label="Open command menu"
          >
            <Search className="w-4 h-4" />
          </button>
        </div>

        {/* Live Metrics & Quick Stats */}
        <div className="flex items-center flex-wrap gap-2 lg:gap-3 text-xs">
          {/* Bankroll Badge (Single Hero Metric in Lemon) */}
          <div className="flex items-center bg-bg-900 border border-border-dark rounded-lg px-3 py-1.5 shadow-inner">
            <span className="text-text-muted mr-2 font-mono text-[11px] uppercase">Bankroll</span>
            <span className="font-display font-light text-lemon tabular-nums text-lg">
              ₦{bankroll.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>

          {/* Daily Exposure Indicator */}
          <div 
            className={`flex items-center bg-bg-900 border rounded-lg px-2.5 py-1.5 transition-colors ${
              exposureNearCap 
                ? "border-coral text-coral" 
                : "border-border-dark text-text-muted"
            }`}
            title="Total bankroll committed today. Hard rule caps daily exposure at 6.0%."
          >
            {exposureNearCap && <AlertTriangle className="w-3.5 h-3.5 mr-1 text-coral" />}
            <span className="font-mono text-[11px] mr-1">Daily:</span>
            <span className="font-semibold text-text-primary tabular-nums">
              {dailyExposurePct.toFixed(1)}%
            </span>
            <span className="text-[10px] text-text-muted ml-0.5">/ 6.0% cap</span>
          </div>

          {/* Freshness Indicator */}
          <div className="flex items-center gap-1.5 bg-bg-900 border border-border-dark rounded-lg px-2.5 py-1.5 text-text-muted">
            <Clock className="w-3.5 h-3.5 text-lavender" />
            <span className="font-mono text-[11px] tabular-nums">{timeAgo}</span>
            <button
              onClick={onRefresh}
              className="ml-1 p-0.5 hover:text-lavender transition-colors"
              title="Refresh live data"
            >
              <RotateCcw className="w-3 h-3" />
            </button>
          </div>

          {/* Desktop Cmdk trigger */}
          <button
            onClick={onOpenCmdk}
            className="hidden md:flex items-center gap-2 bg-bg-900 border border-border-dark hover:border-border-subdued rounded-lg px-2.5 py-1.5 text-text-muted hover:text-text-primary transition-colors cursor-pointer"
          >
            <Search className="w-3.5 h-3.5 text-text-muted" />
            <span className="text-[11px]">Command</span>
            <kbd className="font-mono text-[10px] bg-bg-800 px-1 py-0.5 rounded border border-border-dark text-text-muted">
              Ctrl+K
            </kbd>
          </button>
        </div>
      </div>

      {/* Tabs navigation */}
      <nav className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-2.5 flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-all duration-150 ${
                isActive
                  ? "bg-lavender/15 text-lavender border border-lavender/30 shadow-sm"
                  : "text-text-muted hover:text-text-primary hover:bg-bg-900"
              }`}
            >
              <Icon className={`w-3.5 h-3.5 ${isActive ? "text-lavender" : "text-text-muted"}`} />
              <span>{item.label}</span>
              {item.badge !== null && item.badge !== undefined && (
                <span className="bg-lavender text-bg-950 font-bold px-1.5 py-0.2 rounded-full text-[10px]">
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>
    </header>
  );
}

