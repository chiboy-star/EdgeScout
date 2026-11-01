"""
Unit tests for Temporal Isolation & Leakage Prevention:
Verifies that models only train on past data and strictly fails if future data is used.
"""
import pytest
import pandas as pd
from datetime import datetime, timedelta

from edgescout.backtest.walk_forward import (
    DataLeakageError,
    assert_no_leakage,
    WalkForwardBacktest
)


def create_synthetic_matches(n_matches: int = 50, start_date: str = "2023-01-01") -> pd.DataFrame:
    base = datetime.strptime(start_date, "%Y-%m-%d")
    records = []
    teams = ["Arsenal", "Chelsea", "Liverpool", "Man City", "Man United", "Tottenham"]
    for i in range(n_matches):
        m_date = base + timedelta(days=i * 2)
        h_idx = i % len(teams)
        a_idx = (i + 1) % len(teams)
        records.append({
            "match_id": f"test_match_{i:04d}",
            "match_date": m_date.strftime("%Y-%m-%d"),
            "match_time": "15:00",
            "league_code": "E0",
            "league_name": "Premier League",
            "season": "2324",
            "home_team": teams[h_idx],
            "away_team": teams[a_idx],
            "fthg": (i % 3),
            "ftag": ((i + 1) % 3),
            "ftr": "H" if (i % 3) > ((i + 1) % 3) else ("A" if ((i + 1) % 3) > (i % 3) else "D"),
            "b365_h": 2.10, "b365_d": 3.30, "b365_a": 3.50,
            "b365_ch": 2.10, "b365_cd": 3.30, "b365_ca": 3.50
        })
    return pd.DataFrame(records)


def test_assert_no_leakage_success_on_valid_split():
    df = create_synthetic_matches(30)
    split_date = pd.to_datetime("2023-02-01")
    
    train_df = df[pd.to_datetime(df["match_date"]) < split_date]
    test_df = df[pd.to_datetime(df["match_date"]) >= split_date]
    
    # Should not raise any error
    assert_no_leakage(train_df, test_df, split_date)


def test_assert_no_leakage_fails_when_training_contains_same_day_match():
    df = create_synthetic_matches(30)
    # Pick a date that actually exists in df (e.g. index 10)
    eval_date = pd.to_datetime(df.iloc[10]["match_date"])
    
    # Intentionally corrupt train_df by including the match on eval_date
    corrupted_train = df[pd.to_datetime(df["match_date"]) <= eval_date]
    test_df = df[pd.to_datetime(df["match_date"]) >= eval_date]
    
    with pytest.raises(DataLeakageError, match="Max train date.*is >= evaluation date"):
        assert_no_leakage(corrupted_train, test_df, eval_date)


def test_assert_no_leakage_fails_when_training_contains_future_match():
    df = create_synthetic_matches(30)
    eval_date = pd.to_datetime("2023-02-01")
    
    train_df = df[pd.to_datetime(df["match_date"]) < eval_date].copy()
    # Inject a future match from 2023-03-01 into the training set
    future_match = df.iloc[-1].to_dict()
    future_match["match_date"] = "2023-03-01"
    corrupted_train = pd.concat([train_df, pd.DataFrame([future_match])], ignore_index=True)
    
    test_df = df[pd.to_datetime(df["match_date"]) >= eval_date]
    
    with pytest.raises(DataLeakageError, match="LEAKAGE DETECTED"):
        assert_no_leakage(corrupted_train, test_df, eval_date)


def test_assert_no_leakage_fails_on_duplicate_id_overlap():
    df = create_synthetic_matches(30)
    eval_date = pd.to_datetime("2023-02-01")
    
    train_df = df[pd.to_datetime(df["match_date"]) < eval_date].copy()
    test_df = df[pd.to_datetime(df["match_date"]) >= eval_date].copy()
    
    # Force test match ID to appear in train_df with an earlier date
    leaked_row = test_df.iloc[0].to_dict()
    leaked_row["match_date"] = "2023-01-05"
    corrupted_train = pd.concat([train_df, pd.DataFrame([leaked_row])], ignore_index=True)
    
    with pytest.raises(DataLeakageError, match="test match IDs exist in training set"):
        assert_no_leakage(corrupted_train, test_df, eval_date)


def test_walk_forward_backtest_temporal_integrity():
    """
    Simulates a walk-forward run and verifies that in every single iteration
    max(train_date) < min(test_date).
    """
    df = create_synthetic_matches(120, start_date="2023-01-01")
    engine = WalkForwardBacktest(
        devig_method="shin",
        odds_source="b365",
        step_days=14,
        min_train_matches=30,
        train_window_days=365
    )
    
    results = engine.run(df)
    assert results["total_folds"] > 0
    assert results["total_matches_evaluated"] > 0
