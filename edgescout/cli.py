"""
CLI Entry Point for EdgeScout.
Provides commands for:
- Data ingestion (historical match scores & opening/closing odds)
- Walk-forward backtesting with strict leakage prevention
- Report and calibration curve generation
"""
import argparse
import sys
from pathlib import Path
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from edgescout.config import LEAGUE_CODES, DEFAULT_SEASONS, DEFAULT_DB_PATH, REPORTS_DIR, PLOTS_DIR
from edgescout.data.fetcher import DataFetcher
from edgescout.data.storage import Database
from edgescout.backtest.walk_forward import WalkForwardBacktest
from edgescout.backtest.reporter import (
    generate_ascii_report, 
    generate_calibration_plot, 
    save_markdown_report
)


def cmd_ingest(args):
    print("=== EdgeScout Data Ingestion ===")
    leagues = args.leagues.split(",") if args.leagues else ["E0", "SP1", "I1", "D1", "F1", "CL"]
    seasons = args.seasons.split(",") if args.seasons else DEFAULT_SEASONS
    
    fetcher = DataFetcher()
    db = Database()

    print(f"Target Leagues: {leagues}")
    print(f"Target Seasons: {seasons}")
    
    master_df = fetcher.fetch_all_historical_data(leagues=leagues, seasons=seasons)
    if master_df.empty:
        print("Error: No data retrieved.")
        sys.exit(1)

    print(f"Saving {len(master_df):,} matches into SQLite database: {db.db_path}...")
    db.save_matches_and_odds(master_df)
    print("Ingestion complete. Matches successfully indexed and cached.")


def cmd_backtest(args):
    print("=== EdgeScout Walk-Forward Backtesting Engine ===")
    db = Database()
    matches_df = db.load_clean_dataset(league_code=args.league)

    if matches_df.empty:
        print("Database is empty or missing data. Running ingestion first...")
        fetcher = DataFetcher()
        leagues = [args.league] if args.league else ["E0", "SP1", "I1", "D1", "F1"]
        master_df = fetcher.fetch_all_historical_data(leagues=leagues, seasons=DEFAULT_SEASONS)
        db.save_matches_and_odds(master_df)
        matches_df = db.load_clean_dataset(league_code=args.league)

    print(f"Loaded {len(matches_df):,} clean matches for backtesting.")
    
    engine = WalkForwardBacktest(
        burn_in_seasons=["1213", "1314"],
        step_days=args.step_days,
        train_window_days=args.train_window,
        devig_method=args.devig
    )

    leagues_to_run = [args.league] if args.league else ["E0", "SP1", "I1", "D1", "F1"]
    results = engine.run_all_leagues(matches_df, leagues=leagues_to_run)

    # Output ASCII Report
    ascii_rep = generate_ascii_report(results)
    print("\n" + ascii_rep + "\n")

    # Generate Calibration Plot
    plot_path = PLOTS_DIR / "calibration_plot.png"
    generate_calibration_plot(
        results['calibration']['raw_table'], 
        results['calibration']['calibrated_table'],
        output_path=plot_path
    )
    print(f"Calibration plot saved to: {plot_path}")

    # Generate Markdown Report
    md_path = REPORTS_DIR / "backtest_report.md"
    save_markdown_report(results, output_path=md_path)
    print(f"Detailed Markdown report saved to: {md_path}")


def main():
    parser = argparse.ArgumentParser(description="EdgeScout Quantitative Football Betting System")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Ingest command
    ingest_p = subparsers.add_parser("ingest", help="Ingest historical matches and odds")
    ingest_p.add_argument("--leagues", type=str, default="E0,SP1,I1,D1,F1,CL", help="Comma-separated league codes")
    ingest_p.add_argument("--seasons", type=str, default="2122,2223,2324,2425", help="Comma-separated season codes")

    # Backtest command
    bt_p = subparsers.add_parser("backtest", help="Run walk-forward backtest")
    bt_p.add_argument("--league", type=str, default=None, help="Specific league code (optional)")
    bt_p.add_argument("--devig", type=str, default="shin", choices=["shin", "proportional"], help="De-vig method")
    bt_p.add_argument("--odds-source", type=str, default="b365", choices=["b365", "avg", "ps"], help="Odds provider")
    bt_p.add_argument("--step-days", type=int, default=7, help="Evaluation step window in days")
    bt_p.add_argument("--min-train", type=int, default=200, help="Minimum matches to fit first model")
    bt_p.add_argument("--train-window", type=int, default=730, help="Rolling training window in days")

    args = parser.parse_args()
    if args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "backtest":
        cmd_backtest(args)


if __name__ == "__main__":
    main()

