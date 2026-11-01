"""
Walk-Forward Backtesting Engine for EdgeScout.
Performs:
- Per-league fitting (independent Poisson models per league)
- Strict temporal isolation (training only on past data before evaluation date)
- Real odds only: Bet365 as taken price, Pinnacle Closing de-vigged via Shin as market benchmark
- Like-with-like CLV (Bet365 taken vs Bet365 close) and Pinnacle Closing Value with bootstrap CIs
- Out-of-fold calibration (Temperature/Platt scaling)
- Model + Pinnacle Closing Probability Blend with weight chosen on training folds
- At most ONE bet per match (highest edge)
- Edge distribution audit and suspected model error reporting (>10% edge)
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
    bootstrap_ci,
    bootstrap_log_loss_ci,
    fit_temperature_scaling,
    apply_temperature_scaling,
    fit_market_blend_weight,
    calculate_calibration_curve,
    calculate_expected_calibration_error,
    audit_edge_distribution,
    evaluate_edge_thresholds_single_bet
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
            f"LEAKAGE DETECTED: {len(intersect)} test match IDs exist in training set!"
        )


class WalkForwardBacktest:
    """
    Walk-forward backtesting validator.
    Fits models per league, uses Bet365 as taken price and Pinnacle de-vigged closing line as benchmark.
    """
    def __init__(
        self,
        burn_in_seasons: List[str] = ["1213", "1314"],
        step_days: int = 14,
        train_window_days: int = 730, # 2-year rolling window
        devig_method: str = "shin"
    ):
        self.burn_in_seasons = burn_in_seasons
        self.step_days = step_days
        self.train_window_days = train_window_days
        self.devig_method = devig_method

    def run_league(self, df_league: pd.DataFrame, league_code: str) -> Dict[str, Any]:
        """
        Runs walk-forward backtest for a single league independently.
        """
        df = df_league.copy().sort_values('match_date').reset_index(drop=True)
        df['match_date'] = pd.to_datetime(df['match_date'])
        initial_match_count = len(df)

        # Drop matches with missing REAL odds:
        # Require Bet365 taken odds (b365_h, b365_d, b365_a) AND Pinnacle Closing odds (ps_ch, ps_cd, ps_ca)
        valid_mask = (
            df['b365_h'].notna() & (df['b365_h'] > 1.0) &
            df['b365_d'].notna() & (df['b365_d'] > 1.0) &
            df['b365_a'].notna() & (df['b365_a'] > 1.0) &
            df['ps_ch'].notna() & (df['ps_ch'] > 1.0) &
            df['ps_cd'].notna() & (df['ps_cd'] > 1.0) &
            df['ps_ca'].notna() & (df['ps_ca'] > 1.0) &
            df['ftr'].isin(['H', 'D', 'A'])
        )
        dropped_count = int((~valid_mask).sum())
        df = df[valid_mask].reset_index(drop=True)

        # Identify evaluation start date based on burn-in seasons
        burn_in_matches = df[df['season'].isin(self.burn_in_seasons)]
        if burn_in_matches.empty:
            eval_start_date = df.iloc[min(200, len(df)-1)]['match_date']
        else:
            eval_start_date = burn_in_matches['match_date'].max() + timedelta(days=1)

        end_date = df['match_date'].max()

        current_eval_date = eval_start_date
        all_evaluations = []
        all_bet_records = []
        model_predictions = []
        market_predictions = []
        actual_results = []
        folds_count = 0

        # Maintain training predictions history for out-of-fold calibration
        train_hist_y = []
        train_hist_model_p = []
        train_hist_mkt_p = []

        while current_eval_date <= end_date:
            fold_end_date = current_eval_date + timedelta(days=self.step_days)

            # Training set: strictly before current_eval_date within rolling window
            window_start_date = current_eval_date - timedelta(days=self.train_window_days)
            train_mask = (df['match_date'] < current_eval_date) & (df['match_date'] >= window_start_date)
            train_data = df[train_mask]

            test_mask = (df['match_date'] >= current_eval_date) & (df['match_date'] < fold_end_date)
            test_data = df[test_mask]

            if test_data.empty:
                current_eval_date = fold_end_date
                continue

            if len(train_data) < 50:
                current_eval_date = fold_end_date
                continue

            # Strict temporal leakage assertion
            assert_no_leakage(train_data, test_data, current_eval_date)
            folds_count += 1

            # Fit independent Dixon-Coles model on this league's training window
            dc_model = DixonColesModel()
            try:
                dc_model.fit(train_data, current_date=current_eval_date)
            except Exception:
                current_eval_date = fold_end_date
                continue

            # Calibration and blend weights optimization using training history
            temperature = 1.0
            blend_w = 0.0
            if len(train_hist_y) >= 100:
                y_hist = train_hist_y[-1000:]
                m_hist = np.array(train_hist_model_p[-1000:])
                mkt_hist = np.array(train_hist_mkt_p[-1000:])
                temperature = fit_temperature_scaling(y_hist, m_hist)
                blend_w = fit_market_blend_weight(y_hist, m_hist, mkt_hist)

            # Evaluate test matches in fold
            fold_model_probs = []
            fold_mkt_probs = []
            fold_y = []

            for _, row in test_data.iterrows():
                h_team = row['home_team']
                a_team = row['away_team']
                ftr = row['ftr']

                b365_odds = [float(row['b365_h']), float(row['b365_d']), float(row['b365_a'])]
                pin_close_odds = [float(row['ps_ch']), float(row['ps_cd']), float(row['ps_ca'])]

                # Bet365 Closing odds (where available)
                b365_close_h = float(row['b365_ch']) if pd.notna(row.get('b365_ch')) and float(row.get('b365_ch')) > 1.0 else None
                b365_close_d = float(row['b365_cd']) if pd.notna(row.get('b365_cd')) and float(row.get('b365_cd')) > 1.0 else None
                b365_close_a = float(row['b365_ca']) if pd.notna(row.get('b365_ca')) and float(row.get('b365_ca')) > 1.0 else None
                b365_close_vec = [b365_close_h, b365_close_d, b365_close_a]

                # Raw model probabilities
                probs_dict = dc_model.predict_probabilities(h_team, a_team)
                raw_model_p = np.array([probs_dict['H'], probs_dict['D'], probs_dict['A']])

                # De-vig Pinnacle closing odds via Shin
                try:
                    pin_close_fair, _ = remove_margin(pin_close_odds, method=self.devig_method), 0.0
                except Exception:
                    pin_close_fair = np.array([1.0/o for o in pin_close_odds])
                    pin_close_fair /= pin_close_fair.sum()

                # Calibrated model probabilities using training temperature
                cal_model_p = apply_temperature_scaling(raw_model_p.reshape(1, -1), temperature)[0]

                fold_model_probs.append(raw_model_p)
                fold_mkt_probs.append(pin_close_fair)
                fold_y.append(ftr)

                model_predictions.append(raw_model_p)
                market_predictions.append(pin_close_fair)
                actual_results.append(ftr)

                eval_entry = {
                    'match_id': row['match_id'],
                    'date': row['match_date'],
                    'league': league_code,
                    'home_team': h_team,
                    'away_team': a_team,
                    'ftr': ftr,
                    'p_home': raw_model_p[0],
                    'p_draw': raw_model_p[1],
                    'p_away': raw_model_p[2],
                    'cal_p_home': cal_model_p[0],
                    'cal_p_draw': cal_model_p[1],
                    'cal_p_away': cal_model_p[2],
                    'pin_close_home': pin_close_fair[0],
                    'pin_close_draw': pin_close_fair[1],
                    'pin_close_away': pin_close_fair[2],
                    'b365_h': b365_odds[0],
                    'b365_d': b365_odds[1],
                    'b365_a': b365_odds[2],
                    'temperature': temperature,
                    'blend_w': blend_w
                }
                all_evaluations.append(eval_entry)

                # Record potential bets for H, D, A
                selections = [
                    ('H', raw_model_p[0], cal_model_p[0], pin_close_fair[0], b365_odds[0], b365_close_vec[0]),
                    ('D', raw_model_p[1], cal_model_p[1], pin_close_fair[1], b365_odds[1], b365_close_vec[1]),
                    ('A', raw_model_p[2], cal_model_p[2], pin_close_fair[2], b365_odds[2], b365_close_vec[2]),
                ]

                for sel, p_m, p_cal, p_pin_fair, o_taken, o_b365_close in selections:
                    # Edge defined as expected value against Bet365 taken odds
                    edge = calculate_ev(p_m, o_taken)
                    edge_cal = calculate_ev(p_cal, o_taken)

                    # Like-with-like Bet365 CLV
                    clv_b365 = (o_taken / o_b365_close - 1.0) if o_b365_close else None

                    # Pinnacle closing de-vigged value
                    clv_pinnacle = (p_pin_fair * o_taken) - 1.0

                    won = 1 if ftr == sel else 0

                    all_bet_records.append({
                        'match_id': row['match_id'],
                        'date': row['match_date'],
                        'league': league_code,
                        'home_team': h_team,
                        'away_team': a_team,
                        'selection': sel,
                        'model_prob': p_m,
                        'cal_model_prob': p_cal,
                        'market_prob_pin': p_pin_fair,
                        'fair_odds': calculate_fair_odds(p_m),
                        'odds_taken': o_taken,
                        'odds_b365_close': o_b365_close,
                        'edge': edge,
                        'edge_cal': edge_cal,
                        'clv_b365': clv_b365,
                        'clv_pinnacle': clv_pinnacle,
                        'actual_result': ftr,
                        'won': won
                    })

            # Append fold results to training history for subsequent folds
            train_hist_y.extend(fold_y)
            train_hist_model_p.extend(fold_model_probs)
            train_hist_mkt_p.extend(fold_mkt_probs)

            current_eval_date = fold_end_date

        return {
            'league_code': league_code,
            'initial_match_count': initial_match_count,
            'dropped_count': dropped_count,
            'evaluated_count': len(all_evaluations),
            'folds_count': folds_count,
            'eval_start_date': str(eval_start_date.date()) if hasattr(eval_start_date, 'date') else str(eval_start_date),
            'end_date': str(end_date.date()) if hasattr(end_date, 'date') else str(end_date),
            'evaluations_df': pd.DataFrame(all_evaluations),
            'bets_df': pd.DataFrame(all_bet_records)
        }

    def run_all_leagues(self, df: pd.DataFrame, leagues: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Executes per-league walk-forward runs and aggregates out-of-sample evaluations.
        """
        target_leagues = leagues or ["E0", "SP1", "I1", "D1", "F1"]
        league_results = {}
        all_evals = []
        all_bets = []

        total_initial = 0
        total_dropped = 0
        total_evaluated = 0

        for l_code in target_leagues:
            l_df = df[df['league_code'] == l_code]
            if l_df.empty:
                continue
            print(f"Running Walk-Forward Backtest for league {l_code} ({len(l_df)} matches)...")
            res = self.run_league(l_df, l_code)
            league_results[l_code] = res
            total_initial += res['initial_match_count']
            total_dropped += res['dropped_count']
            total_evaluated += res['evaluated_count']
            all_evals.append(res['evaluations_df'])
            all_bets.append(res['bets_df'])

        master_evals = pd.concat(all_evals, ignore_index=True) if all_evals else pd.DataFrame()
        master_bets = pd.concat(all_bets, ignore_index=True) if all_bets else pd.DataFrame()

        if master_evals.empty:
            raise RuntimeError("No evaluations generated across any league.")

        # Extract model and market probability arrays
        model_p_arr = master_evals[['p_home', 'p_draw', 'p_away']].values
        cal_p_arr = master_evals[['cal_p_home', 'cal_p_draw', 'cal_p_away']].values
        pin_close_p_arr = master_evals[['pin_close_home', 'pin_close_draw', 'pin_close_away']].values
        y_true = master_evals['ftr'].tolist()

        # Compute Log Loss and Bootstrap CIs
        model_ll, model_ll_lo, model_ll_hi = bootstrap_log_loss_ci(y_true, model_p_arr)
        cal_ll, cal_ll_lo, cal_ll_hi = bootstrap_log_loss_ci(y_true, cal_p_arr)
        pin_ll, pin_ll_lo, pin_ll_hi = bootstrap_log_loss_ci(y_true, pin_close_p_arr)

        # Evaluate Model + Pinnacle Closing Blend
        # Compute blend probability on held-out folds using the blend weight chosen on training folds
        w_vals = master_evals['blend_w'].values.reshape(-1, 1)
        blend_p_arr = w_vals * model_p_arr + (1.0 - w_vals) * pin_close_p_arr
        blend_ll, blend_ll_lo, blend_ll_hi = bootstrap_log_loss_ci(y_true, blend_p_arr)

        # Brier scores
        model_brier = multiclass_brier_score(y_true, model_p_arr)
        cal_brier = multiclass_brier_score(y_true, cal_p_arr)
        pin_brier = multiclass_brier_score(y_true, pin_close_p_arr)

        # Probability Calibration Curves (Raw vs Calibrated)
        all_pred_raw = model_p_arr.flatten()
        all_pred_cal = cal_p_arr.flatten()
        mapping = {'H': 0, 'D': 1, 'A': 2}
        all_actuals = np.zeros(len(all_pred_raw))
        for i, res in enumerate(y_true):
            all_actuals[i*3 + mapping[res]] = 1.0

        calib_raw_df = calculate_calibration_curve(all_pred_raw, all_actuals)
        calib_cal_df = calculate_calibration_curve(all_pred_cal, all_actuals)
        ece_raw = calculate_expected_calibration_error(calib_raw_df)
        ece_cal = calculate_expected_calibration_error(calib_cal_df)

        # Like-with-like CLV statistics with bootstrap CIs
        valid_b365_clv = master_bets['clv_b365'].dropna().values
        b365_clv_mean, b365_clv_lo, b365_clv_hi = bootstrap_ci(valid_b365_clv) if len(valid_b365_clv) > 0 else (0.0, 0.0, 0.0)
        b365_beat_pct, b365_beat_lo, b365_beat_hi = bootstrap_ci(
            (valid_b365_clv > 0).astype(float) * 100.0
        ) if len(valid_b365_clv) > 0 else (0.0, 0.0, 0.0)

        # Pinnacle Closing Value statistics with bootstrap CIs
        valid_pin_clv = master_bets['clv_pinnacle'].dropna().values
        pin_clv_mean, pin_clv_lo, pin_clv_hi = bootstrap_ci(valid_pin_clv)
        pin_beat_pct, pin_beat_lo, pin_beat_hi = bootstrap_ci(
            (valid_pin_clv > 0).astype(float) * 100.0
        )

        # Edge Distribution Audit & Suspected Model Errors
        edge_audit = audit_edge_distribution(master_bets)

        # Flat-Stake Performance with Single Bet per Match constraint
        edge_thresholds_summary = evaluate_edge_thresholds_single_bet(master_bets)

        return {
            'total_initial_matches': total_initial,
            'total_dropped_matches': total_dropped,
            'total_evaluated_matches': total_evaluated,
            'leagues_evaluated': target_leagues,
            'league_results': league_results,
            'log_loss': {
                'model': (model_ll, model_ll_lo, model_ll_hi),
                'calibrated_model': (cal_ll, cal_ll_lo, cal_ll_hi),
                'market_pinnacle': (pin_ll, pin_ll_lo, pin_ll_hi),
                'blend': (blend_ll, blend_ll_lo, blend_ll_hi)
            },
            'brier_score': {
                'model': model_brier,
                'calibrated_model': cal_brier,
                'market_pinnacle': pin_brier
            },
            'calibration': {
                'raw_table': calib_raw_df,
                'calibrated_table': calib_cal_df,
                'ece_raw': ece_raw,
                'ece_cal': ece_cal
            },
            'clv': {
                'b365_like_with_like': {
                    'count': len(valid_b365_clv),
                    'mean': (b365_clv_mean, b365_clv_lo, b365_clv_hi),
                    'beat_close_pct': (b365_beat_pct, b365_beat_lo, b365_beat_hi)
                },
                'pinnacle_devigged': {
                    'count': len(valid_pin_clv),
                    'mean': (pin_clv_mean, pin_clv_lo, pin_clv_hi),
                    'beat_close_pct': (pin_beat_pct, pin_beat_lo, pin_beat_hi)
                }
            },
            'edge_audit': edge_audit,
            'edge_thresholds_summary': edge_thresholds_summary,
            'evaluations_df': master_evals,
            'bets_df': master_bets
        }
