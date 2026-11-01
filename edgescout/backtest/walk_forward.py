"""
Walk-Forward Backtesting Engine for EdgeScout.
Enforces strict temporal separation: models are trained ONLY on data strictly
before each evaluation date. Includes built-in leakage verification assertions.
"""
import pandas as pd
import numpy as np
from datetime import timedelta
from typing import Dict, List, Optional, Tuple, Any

from edgescout.models.dixon_coles import DixonColesModel
from edgescout.models.margin import remove_margin, calculate_ev, calculate_fair_odds
from edgescout.backtest.metrics import (
    multiclass_log_loss,
    multiclass_brier_score,
    calculate_calibration_curve,
    calculate_expected_calibration_error,
    calculate_clv,
    evaluate_edge_thresholds
)


class DataLeakageError(Exception):
    """Raised when future data or target match data leaks into the training window."""
    pass


def assert_no_leakage(
    train_df: pd.DataFrame, 
    test_df: pd.DataFrame, 
    eval_date: pd.Timestamp
):
    """
    Strictly asserts that:
    1. Maximum training match date is strictly less than the evaluation date.
    2. No test match ID appears in the training set.
    3. Test matches have not yet occurred relative to evaluation date.
    """
    if train_df.empty or test_df.empty:
        return

    max_train_date = pd.to_datetime(train_df['match_date']).max()
    min_test_date = pd.to_datetime(test_df['match_date']).min()
    eval_date_ts = pd.to_datetime(eval_date)

    if max_train_date >= eval_date_ts:
        raise DataLeakageError(
            f"LEAKAGE DETECTED: Max train date ({max_train_date}) is >= evaluation date ({eval_date_ts})!"
        )

    if max_train_date >= min_test_date:
        raise DataLeakageError(
            f"LEAKAGE DETECTED: Max train date ({max_train_date}) is >= Min test date ({min_test_date})!"
        )

    train_ids = set(train_df['match_id'])
    test_ids = set(test_df['match_id'])
    intersect = train_ids.intersection(test_ids)
    if intersect:
        raise DataLeakageError(
            f"LEAKAGE DETECTED: {len(intersect)} test match IDs exist in training set! Examples: {list(intersect)[:3]}"
        )


class WalkForwardBacktest:
    """
    Walk-forward backtesting validator.
    Simulates real-world betting where odds are taken ahead of time and evaluated
    against closing lines and match outcomes.
    """
    def __init__(
        self,
        devig_method: str = "shin",
        odds_source: str = "b365",       # 'b365', 'avg', or 'ps'
        step_days: int = 7,              # Retrain weekly
        min_train_matches: int = 200,    # Minimum historical matches before starting backtest
        train_window_days: int = 730     # 2-year rolling window
    ):
        self.devig_method = devig_method
        self.odds_source = odds_source
        self.step_days = step_days
        self.min_train_matches = min_train_matches
        self.train_window_days = train_window_days

    def run(self, matches_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Executes walk-forward backtest over chronological match data.
        """
        df = matches_df.copy().sort_values('match_date').reset_index(drop=True)
        df['match_date'] = pd.to_datetime(df['match_date'])

        # Identify relevant odds columns
        h_col = f"{self.odds_source}_h"
        d_col = f"{self.odds_source}_d"
        a_col = f"{self.odds_source}_a"
        ch_col = f"{self.odds_source}_ch"
        cd_col = f"{self.odds_source}_cd"
        ca_col = f"{self.odds_source}_ca"

        # Filter valid rows having required odds and results
        valid_mask = (
            df[h_col].notna() & (df[h_col] > 1.0) &
            df[d_col].notna() & (df[d_col] > 1.0) &
            df[a_col].notna() & (df[a_col] > 1.0) &
            df['ftr'].isin(['H', 'D', 'A'])
        )
        df = df[valid_mask].reset_index(drop=True)

        if len(df) <= self.min_train_matches:
            raise ValueError(f"Insufficient matches ({len(df)}) for minimum training requirement ({self.min_train_matches}).")

        start_date = df.iloc[self.min_train_matches]['match_date']
        end_date = df['match_date'].max()

        print(f"Starting Walk-Forward Backtest from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        print(f"Total available matches: {len(df)} across {df['league_code'].nunique()} leagues")

        current_eval_date = start_date
        all_evaluations = []
        all_bet_records = []
        model_predictions = []
        market_predictions = []
        actual_results = []

        total_folds = 0

        while current_eval_date <= end_date:
            fold_end_date = current_eval_date + timedelta(days=self.step_days)

            # Training set: strictly BEFORE current_eval_date, optionally bounded by train_window_days
            window_start_date = current_eval_date - timedelta(days=self.train_window_days)
            train_mask = (df['match_date'] < current_eval_date) & (df['match_date'] >= window_start_date)
            train_data = df[train_mask]

            # Test set: matches in this step window [current_eval_date, fold_end_date)
            test_mask = (df['match_date'] >= current_eval_date) & (df['match_date'] < fold_end_date)
            test_data = df[test_mask]

            if len(test_data) == 0:
                current_eval_date = fold_end_date
                continue

            if len(train_data) < self.min_train_matches:
                current_eval_date = fold_end_date
                continue

            # Strict Leakage Assertion on every single fold
            assert_no_leakage(train_data, test_data, current_eval_date)

            total_folds += 1

            # Fit Dixon-Coles model
            dc_model = DixonColesModel()
            try:
                dc_model.fit(train_data, current_date=current_eval_date)
            except Exception as e:
                current_eval_date = fold_end_date
                continue

            # Evaluate test matches
            for _, row in test_data.iterrows():
                h_team = row['home_team']
                a_team = row['away_team']
                ftr = row['ftr']

                odds_taken_vec = [float(row[h_col]), float(row[d_col]), float(row[a_col])]
                
                # Closing odds (fallback to taken odds if missing)
                odds_close_h = float(row[ch_col]) if pd.notna(row.get(ch_col)) else odds_taken_vec[0]
                odds_close_d = float(row[cd_col]) if pd.notna(row.get(cd_col)) else odds_taken_vec[1]
                odds_close_a = float(row[ca_col]) if pd.notna(row.get(ca_col)) else odds_taken_vec[2]
                odds_close_vec = [odds_close_h, odds_close_d, odds_close_a]

                # Model probabilities
                probs = dc_model.predict_probabilities(h_team, a_team)
                m_probs = [probs['H'], probs['D'], probs['A']]

                # De-vig market probabilities
                try:
                    market_fair = remove_margin(odds_taken_vec, method=self.devig_method)
                except Exception:
                    market_fair = np.array([1.0/o for o in odds_taken_vec])
                    market_fair /= np.sum(market_fair)

                model_predictions.append(m_probs)
                market_predictions.append(market_fair.tolist())
                actual_results.append(ftr)

                eval_entry = {
                    'match_id': row['match_id'],
                    'date': row['match_date'],
                    'league': row['league_code'],
                    'home_team': h_team,
                    'away_team': a_team,
                    'ftr': ftr,
                    'p_home': m_probs[0],
                    'p_draw': m_probs[1],
                    'p_away': m_probs[2],
                    'm_home': market_fair[0],
                    'm_draw': market_fair[1],
                    'm_away': market_fair[2],
                    'odds_h': odds_taken_vec[0],
                    'odds_d': odds_taken_vec[1],
                    'odds_a': odds_taken_vec[2],
                    'close_h': odds_close_vec[0],
                    'close_d': odds_close_vec[1],
                    'close_a': odds_close_vec[2]
                }
                all_evaluations.append(eval_entry)

                # Check edge for H, D, A
                selections = [
                    ('H', m_probs[0], market_fair[0], odds_taken_vec[0], odds_close_vec[0]),
                    ('D', m_probs[1], market_fair[1], odds_taken_vec[1], odds_close_vec[1]),
                    ('A', m_probs[2], market_fair[2], odds_taken_vec[2], odds_close_vec[2]),
                ]

                for sel, p_m, p_mkt, o_taken, o_close in selections:
                    edge = calculate_ev(p_m, o_taken)
                    clv = calculate_clv(o_taken, o_close)
                    won = 1 if ftr == sel else 0

                    all_bet_records.append({
                        'match_id': row['match_id'],
                        'date': row['match_date'],
                        'league': row['league_code'],
                        'home_team': h_team,
                        'away_team': a_team,
                        'selection': sel,
                        'model_prob': p_m,
                        'market_prob': p_mkt,
                        'fair_odds': calculate_fair_odds(p_m),
                        'odds_taken': o_taken,
                        'closing_odds': o_close,
                        'edge': edge,
                        'clv': clv,
                        'actual_result': ftr,
                        'won': won
                    })

            current_eval_date = fold_end_date

        if not model_predictions:
            raise RuntimeError("No predictions generated during walk-forward backtest.")

        model_preds_arr = np.array(model_predictions)
        market_preds_arr = np.array(market_predictions)
        bets_df = pd.DataFrame(all_bet_records)
        evals_df = pd.DataFrame(all_evaluations)

        # Probabilistic scores
        model_logloss = multiclass_log_loss(actual_results, model_preds_arr)
        market_logloss = multiclass_log_loss(actual_results, market_preds_arr)
        uniform_logloss = -np.log(1.0 / 3.0)

        model_brier = multiclass_brier_score(actual_results, model_preds_arr)
        market_brier = multiclass_brier_score(actual_results, market_preds_arr)
        uniform_brier = 2.0 / 3.0

        # Calibration across all outcomes
        all_predicted = []
        all_actuals = []
        mapping = {'H': 0, 'D': 1, 'A': 2}
        for i, res in enumerate(actual_results):
            for k in range(3):
                all_predicted.append(model_preds_arr[i, k])
                all_actuals.append(1 if mapping[res] == k else 0)

        calib_df = calculate_calibration_curve(np.array(all_predicted), np.array(all_actuals))
        ece = calculate_expected_calibration_error(calib_df)

        # Flat-stake ROI across thresholds
        edge_thresholds_df = evaluate_edge_thresholds(bets_df)

        return {
            'total_matches_evaluated': len(evals_df),
            'total_folds': total_folds,
            'start_date': str(start_date.date()),
            'end_date': str(end_date.date()),
            'model_log_loss': model_logloss,
            'market_log_loss': market_logloss,
            'uniform_log_loss': uniform_logloss,
            'model_brier_score': model_brier,
            'market_brier_score': market_brier,
            'uniform_brier_score': uniform_brier,
            'expected_calibration_error': ece,
            'calibration_table': calib_df,
            'edge_thresholds_summary': edge_thresholds_df,
            'bets_df': bets_df,
            'evaluations_df': evals_df
        }

