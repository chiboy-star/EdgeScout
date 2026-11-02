"use client";

import React, { useEffect } from "react";
import { Command } from "cmdk";
import { 
  Sparkles, 
  Calendar, 
  BookOpen, 
  Layers, 
  FlaskConical, 
  TrendingUp, 
  RotateCcw, 
  Calculator,
  RefreshCw,
  X
} from "lucide-react";

interface CommandMenuProps {
  open: boolean;
  setOpen: (open: boolean) => void;
  setActiveTab: (tab: string) => void;
  onAutoSettle: () => void;
  onResetBankroll: () => void;
  onOpenCustomOdds: () => void;
}

export function CommandMenu({
  open,
  setOpen,
  setActiveTab,
  onAutoSettle,
  onResetBankroll,
  onOpenCustomOdds,
}: CommandMenuProps) {
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || e.key === "/") {
        e.preventDefault();
        setOpen(!open);
      }
      if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [open, setOpen]);

  if (!open) return null;

  const navigateTo = (tab: string) => {
    setActiveTab(tab);
    setOpen(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-bg-950/80 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="w-full max-w-lg bg-bg-900 border border-border-subdued rounded-2xl shadow-2xl overflow-hidden">
        <Command className="w-full">
          <div className="flex items-center px-4 border-b border-border-dark">
            <Command.Input
              autoFocus
              placeholder="Type a command or jump to screen..."
              className="w-full py-3.5 bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
            />
            <button
              onClick={() => setOpen(false)}
              className="p-1 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-800"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <Command.List className="max-h-72 overflow-y-auto p-2 text-xs space-y-1">
            <Command.Empty className="py-6 text-center text-text-muted">
              No matching commands found.
            </Command.Empty>

            <Command.Group heading="Navigation" className="text-[11px] font-mono text-text-muted px-2 py-1">
              <Command.Item
                onSelect={() => navigateTo("shortlist")}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-text-primary hover:bg-bg-800 cursor-pointer transition-colors"
              >
                <Sparkles className="w-4 h-4 text-lemon" />
                <span>Today (Suggestion Shortlist)</span>
              </Command.Item>
              <Command.Item
                onSelect={() => navigateTo("fixtures")}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-text-primary hover:bg-bg-800 cursor-pointer transition-colors"
              >
                <Calendar className="w-4 h-4 text-lavender" />
                <span>This Week (Market View & Facts)</span>
              </Command.Item>
              <Command.Item
                onSelect={() => navigateTo("ledger")}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-text-primary hover:bg-bg-800 cursor-pointer transition-colors"
              >
                <BookOpen className="w-4 h-4 text-text-primary" />
                <span>Paper Ledger & Settle</span>
              </Command.Item>
              <Command.Item
                onSelect={() => navigateTo("accumulator")}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-text-primary hover:bg-bg-800 cursor-pointer transition-colors"
              >
                <Layers className="w-4 h-4 text-coral" />
                <span>Accumulator Cost Calculator</span>
              </Command.Item>
              <Command.Item
                onSelect={() => navigateTo("strategy")}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-text-primary hover:bg-bg-800 cursor-pointer transition-colors"
              >
                <FlaskConical className="w-4 h-4 text-lavender" />
                <span>Strategy Tester (13 Seasons)</span>
              </Command.Item>
              <Command.Item
                onSelect={() => navigateTo("performance")}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-text-primary hover:bg-bg-800 cursor-pointer transition-colors"
              >
                <TrendingUp className="w-4 h-4 text-lemon" />
                <span>Performance & Equity Curve</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="Actions" className="text-[11px] font-mono text-text-muted px-2 py-1 mt-2">
              <Command.Item
                onSelect={() => {
                  setOpen(false);
                  onAutoSettle();
                }}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-text-primary hover:bg-bg-800 cursor-pointer transition-colors"
              >
                <RefreshCw className="w-4 h-4 text-lemon" />
                <span>Auto-settle open bets from real results feed</span>
              </Command.Item>

              <Command.Item
                onSelect={() => {
                  setOpen(false);
                  onOpenCustomOdds();
                }}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-text-primary hover:bg-bg-800 cursor-pointer transition-colors"
              >
                <Calculator className="w-4 h-4 text-lavender" />
                <span>Enter manual SportyBet decimal odds</span>
              </Command.Item>

              <Command.Item
                onSelect={() => {
                  setOpen(false);
                  onResetBankroll();
                }}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-coral hover:bg-bg-800 cursor-pointer transition-colors"
              >
                <RotateCcw className="w-4 h-4 text-coral" />
                <span>Reset virtual bankroll to ₦100,000</span>
              </Command.Item>
            </Command.Group>
          </Command.List>

          <div className="border-t border-border-dark px-4 py-2 text-[11px] text-text-muted flex items-center justify-between">
            <span>Navigation: <kbd className="px-1 py-0.5 rounded bg-bg-800 border border-border-dark">↑</kbd> <kbd className="px-1 py-0.5 rounded bg-bg-800 border border-border-dark">↓</kbd></span>
            <span>Select: <kbd className="px-1 py-0.5 rounded bg-bg-800 border border-border-dark">↵</kbd></span>
            <span>Close: <kbd className="px-1 py-0.5 rounded bg-bg-800 border border-border-dark">ESC</kbd></span>
          </div>
        </Command>
      </div>
    </div>
  );
}
