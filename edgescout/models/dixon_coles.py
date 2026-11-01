"""
Dixon-Coles & Poisson Football Match Outcome Model.
Implements the Mark Dixon & Stuart Coles (1997) bivariate Poisson formulation
with low-scoring scoreline adjustment (rho), home advantage (gamma), attack/defense
ratings, and exponential time-decay weighting (xi).
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import factorial
from typing import Dict, Tuple, List, Optional, Any


def tau(x: int, y: int, lambda_: float, mu: float, rho: float) -> float:
    """
    Dixon-Coles low-score adjustment factor tau(x, y, lambda, mu, rho).
    Adjusts (0,0), (1,0), (0,1), (1,1) for correlation between scores.
    """
    if x == 0 and y == 0:
        return max(1e-6, 1.0 - lambda_ * mu * rho)
    elif x == 0 and y == 1:
        return max(1e-6, 1.0 + lambda_ * rho)
    elif x == 1 and y == 0:
        return max(1e-6, 1.0 + mu * rho)
    elif x == 1 and y == 1:
        return max(1e-6, 1.0 - rho)
    else:
        return 1.0


class DixonColesModel:
    """
    Dixon-Coles bivariate Poisson model for football match prediction.
    """
    def __init__(self, xi: float = 0.0019, max_goals: int = 10):
        """
        xi: Time decay parameter (approx half-life ~ 365 days)
        max_goals: Maximum goals evaluated per team for score grid
        """
        self.xi = xi
        self.max_goals = max_goals
        self.teams: List[str] = []
        self.team_to_idx: Dict[str, int] = {}
        self.attack_params: Dict[str, float] = {}
        self.defense_params: Dict[str, float] = {}
        self.home_advantage: float = 0.25
        self.rho: float = -0.05
        self.is_fitted: bool = False
        self.mean_home_goals: float = 1.45
        self.mean_away_goals: float = 1.15

    def fit(self, matches_df: pd.DataFrame, current_date: Optional[pd.Timestamp] = None) -> "DixonColesModel":
        """
        Fit model parameters on historical matches strictly prior to current_date.
        matches_df must contain home/away teams, goals, and match date.
        """
        df = matches_df.copy()
        
        # Standardize column names if needed
        col_map = {
            'HomeTeam': 'home_team', 'AwayTeam': 'away_team',
            'FTHG': 'fthg', 'FTAG': 'ftag', 'Date': 'match_date'
        }
        for k, v in col_map.items():
            if k in df.columns and v not in df.columns:
                df[v] = df[k]

        required = ['home_team', 'away_team', 'fthg', 'ftag', 'match_date']
        df = df.dropna(subset=required)
        if len(df) < 10:
            raise ValueError(f"Need at least 10 matches to fit model, got {len(df)}")

        # Ensure Date is datetime
        if not pd.api.types.is_datetime64_any_dtype(df['match_date']):
            df['match_date'] = pd.to_datetime(df['match_date'], dayfirst=True)

        if current_date is not None:
            current_date = pd.to_datetime(current_date)
            # Strict verification: no matches on or after current_date
            df = df[df['match_date'] < current_date]
            if len(df) < 10:
                raise ValueError("Insufficient training matches strictly before evaluation date.")

        ref_date = current_date if current_date is not None else df['match_date'].max()
        
        # Calculate time decay weights w_k = exp(-xi * (ref_date - match_date))
        days_diff = (ref_date - df['match_date']).dt.total_seconds() / (24 * 3600)
        days_diff = np.maximum(0, days_diff.values)
        weights = np.exp(-self.xi * days_diff)

        teams = sorted(list(set(df['home_team']).union(set(df['away_team']))))
        n_teams = len(teams)
        team_to_idx = {team: i for i, team in enumerate(teams)}
        self.teams = teams
        self.team_to_idx = team_to_idx

        home_indices = df['home_team'].map(team_to_idx).values
        away_indices = df['away_team'].map(team_to_idx).values
        fthg = df['fthg'].values.astype(int)
        ftag = df['ftag'].values.astype(int)

        self.mean_home_goals = float(np.average(fthg, weights=weights))
        self.mean_away_goals = float(np.average(ftag, weights=weights))

        # Initial parameter estimates using empirical attack / defense log ratios
        init_att = np.zeros(n_teams)
        init_def = np.zeros(n_teams)

        for i, t in enumerate(teams):
            h_scored = weights[home_indices == i] * fthg[home_indices == i]
            a_scored = weights[away_indices == i] * ftag[away_indices == i]
            h_w = weights[home_indices == i].sum()
            a_w = weights[away_indices == i].sum()
            
            tot_scored = (h_scored.sum() + a_scored.sum()) / max(1e-3, h_w + a_w)
            avg_league = (self.mean_home_goals + self.mean_away_goals) / 2.0
            init_att[i] = np.log(max(0.3, tot_scored / avg_league))

            h_conc = weights[home_indices == i] * ftag[home_indices == i]
            a_conc = weights[away_indices == i] * fthg[away_indices == i]
            tot_conc = (h_conc.sum() + a_conc.sum()) / max(1e-3, h_w + a_w)
            init_def[i] = -np.log(max(0.3, tot_conc / avg_league))

        init_att -= np.mean(init_att)
        init_def -= np.mean(init_def)
        init_gamma = 0.25
        init_rho = -0.05

        x0 = np.concatenate([init_att[:-1], init_def, [init_gamma, init_rho]])

        def loss(params: np.ndarray) -> float:
            att = np.append(params[:n_teams-1], -np.sum(params[:n_teams-1]))
            defense = params[n_teams-1: 2*n_teams-1]
            gamma = params[2*n_teams-1]
            rho = params[2*n_teams]

            penalty = 0.0
            if rho < -0.25 or rho > 0.25:
                penalty += 1000.0 * (abs(rho) - 0.25)**2

            lam = np.exp(att[home_indices] - defense[away_indices] + gamma)
            mu = np.exp(att[away_indices] - defense[home_indices])

            log_lik = fthg * np.log(lam) - lam + ftag * np.log(mu) - mu

            tau_vals = np.ones(len(fthg))
            m00 = (fthg == 0) & (ftag == 0)
            m01 = (fthg == 0) & (ftag == 1)
            m10 = (fthg == 1) & (ftag == 0)
            m11 = (fthg == 1) & (ftag == 1)

            tau_vals[m00] = np.maximum(1e-6, 1.0 - lam[m00] * mu[m00] * rho)
            tau_vals[m01] = np.maximum(1e-6, 1.0 + lam[m01] * rho)
            tau_vals[m10] = np.maximum(1e-6, 1.0 + mu[m10] * rho)
            tau_vals[m11] = np.maximum(1e-6, 1.0 - rho)

            log_lik += np.log(tau_vals)
            weighted_nll = -np.sum(weights * log_lik) + penalty
            return float(weighted_nll)

        res = minimize(loss, x0, method='L-BFGS-B', options={'maxiter': 100})
        
        final_params = res.x if res.success else x0
        att_final = np.append(final_params[:n_teams-1], -np.sum(final_params[:n_teams-1]))
        def_final = final_params[n_teams-1: 2*n_teams-1]
        
        self.home_advantage = float(final_params[2*n_teams-1])
        self.rho = float(np.clip(final_params[2*n_teams], -0.20, 0.20))

        self.attack_params = {t: float(att_final[i]) for i, t in enumerate(teams)}
        self.defense_params = {t: float(def_final[i]) for i, t in enumerate(teams)}
        self.is_fitted = True
        return self

    def predict_expected_goals(self, home_team: str, away_team: str) -> Tuple[float, float]:
        """
        Calculate expected goals (lambda, mu) for a matchup.
        If a team is unseen, uses league average rating (0.0).
        """
        alpha_h = self.attack_params.get(home_team, 0.0)
        beta_a = self.defense_params.get(away_team, 0.0)
        alpha_a = self.attack_params.get(away_team, 0.0)
        beta_h = self.defense_params.get(home_team, 0.0)

        lambda_ = float(np.exp(alpha_h - beta_a + self.home_advantage))
        mu = float(np.exp(alpha_a - beta_h))
        
        # Clip to sensible football range [0.1, 7.0]
        lambda_ = float(np.clip(lambda_, 0.2, 5.5))
        mu = float(np.clip(mu, 0.2, 5.5))
        return lambda_, mu

    def predict_probabilities(
        self, 
        home_team: str, 
        away_team: str
    ) -> Dict[str, float]:
        """
        Predict 1X2 outcome probabilities: P(Home), P(Draw), P(Away).
        Computes the full score probability matrix up to max_goals.
        """
        lambda_, mu = self.predict_expected_goals(home_team, away_team)
        
        # Build goal probability grid
        x_goals = np.arange(self.max_goals + 1)
        y_goals = np.arange(self.max_goals + 1)
        
        p_x = (lambda_ ** x_goals * np.exp(-lambda_)) / factorial(x_goals)
        p_y = (mu ** y_goals * np.exp(-mu)) / factorial(y_goals)
        
        score_matrix = np.outer(p_x, p_y)

        # Apply Dixon-Coles tau adjustment
        score_matrix[0, 0] *= tau(0, 0, lambda_, mu, self.rho)
        score_matrix[0, 1] *= tau(0, 1, lambda_, mu, self.rho)
        score_matrix[1, 0] *= tau(1, 0, lambda_, mu, self.rho)
        score_matrix[1, 1] *= tau(1, 1, lambda_, mu, self.rho)

        # Normalize matrix to handle truncation beyond max_goals
        score_matrix /= np.sum(score_matrix)

        p_home = float(np.sum(np.tril(score_matrix, -1)))
        p_draw = float(np.sum(np.diag(score_matrix)))
        p_away = float(np.sum(np.triu(score_matrix, 1)))

        total = p_home + p_draw + p_away
        return {
            "H": p_home / total,
            "D": p_draw / total,
            "A": p_away / total,
            "lambda": lambda_,
            "mu": mu
        }
