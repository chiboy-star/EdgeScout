"""
Unit tests for Dixon-Coles and Poisson statistical engine.
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from edgescout.models.dixon_coles import DixonColesModel, tau


def test_tau_low_scores_adjustment():
    # Verify Dixon-Coles tau adjustment logic
    lambda_ = 1.4
    mu = 1.1
    rho = -0.05
    
    # (0,0) with negative rho should have tau > 1
    t00 = tau(0, 0, lambda_, mu, rho)
    assert t00 > 1.0 # 1 - (1.4 * 1.1 * -0.05) = 1 + 0.077 = 1.077
    assert pytest.approx(t00, abs=1e-4) == 1.077

    # High scores should have tau == 1.0
    assert tau(2, 1, lambda_, mu, rho) == 1.0
    assert tau(3, 0, lambda_, mu, rho) == 1.0


def test_dixon_coles_fit_and_predict_probabilities():
    # Build synthetic training matches
    records = []
    teams = ["TeamA", "TeamB", "TeamC", "TeamD"]
    base_date = datetime(2023, 1, 1)

    for i in range(60):
        h = teams[i % 4]
        a = teams[(i + 1) % 4]
        records.append({
            "HomeTeam": h,
            "AwayTeam": a,
            "FTHG": (i % 3) + 1,
            "FTAG": (i % 2),
            "Date": base_date + timedelta(days=i)
        })
    df = pd.DataFrame(records)

    model = DixonColesModel(xi=0.002, max_goals=8)
    model.fit(df)

    assert model.is_fitted
    assert len(model.attack_params) == 4
    assert len(model.defense_params) == 4

    probs = model.predict_probabilities("TeamA", "TeamB")
    
    assert "H" in probs and "D" in probs and "A" in probs
    assert probs["H"] > 0.0 and probs["D"] > 0.0 and probs["A"] > 0.0
    # Probabilities must sum to 1.0
    total_prob = probs["H"] + probs["D"] + probs["A"]
    assert pytest.approx(total_prob, abs=1e-6) == 1.0


def test_unseen_team_graceful_fallback():
    # Verify that predicting an unseen opponent does not raise an unhandled exception
    records = []
    teams = ["TeamA", "TeamB", "TeamC"]
    base_date = datetime(2023, 1, 1)

    for i in range(30):
        records.append({
            "HomeTeam": teams[i % 3],
            "AwayTeam": teams[(i + 1) % 3],
            "FTHG": 1,
            "FTAG": 1,
            "Date": base_date + timedelta(days=i)
        })
    df = pd.DataFrame(records)

    model = DixonColesModel()
    model.fit(df)

    # TeamNew is not in training set
    probs = model.predict_probabilities("TeamA", "TeamNew")
    total = probs["H"] + probs["D"] + probs["A"]
    assert pytest.approx(total, abs=1e-6) == 1.0

