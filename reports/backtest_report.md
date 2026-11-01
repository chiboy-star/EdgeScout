# EdgeScout Quantitative Audit & Backtest Report

```
==========================================================================================
                     EDGESCOUT QUANTITATIVE AUDIT & BACKTEST REPORT
==========================================================================================

*** HEADLINE: MODEL DOES NOT BEAT THE PINNACLE CLOSING LINE. ZERO ALPHA OVER THE SHARP CLOSE. ***

Historical Coverage : 2012/13 through 2024/25 (13 full seasons, 2-season burn-in)
Model Fitting       : Independent per-league fitting (E0, SP1, I1, D1, F1)
Odds Definition     : Taken Price = Bet365 | Market Probability = Pinnacle Closing (Shin)
Single Bet Policy   : Enforced (at most ONE bet per match on highest-edge outcome)
Total Matches Ingest: 23,489
Matches Dropped     : 10 (due to missing real Bet365/Pinnacle odds)
Matches Evaluated   : 19,829 (out-of-sample)
------------------------------------------------------------------------------------------
1. THE KEY TEST: LOG LOSS COMPARISON (WITH 95% BOOTSTRAP CONFIDENCE INTERVALS)
------------------------------------------------------------------------------------------
Specification                  | Log Loss     | 95% Bootstrap CI         | Brier Score 
------------------------------------------------------------------------------------------
EdgeScout Model (Raw)          | 0.9907       | [0.9839, 0.9975]       | 0.5901      
EdgeScout Model (Calibrated)   | 0.9906       | [0.9845, 0.9969]       | 0.5903      
Pinnacle Closing (De-Vigged)   | 0.9637       | [0.9568, 0.9700]       | 0.5724      
Model + Pinnacle Blend         | 0.9639       | [0.9570, 0.9703]       | N/A         
------------------------------------------------------------------------------------------
Interpretation: Market closing Log Loss (0.9637) is strictly superior to model alone (0.9907).
The training-optimized blend weight collapses toward the market (w -> 0.0), failing to beat Pinnacle.

2. CLOSING LINE VALUE (CLV) AUDIT (WITH 95% BOOTSTRAP CONFIDENCE INTERVALS)
------------------------------------------------------------------------------------------
A. Like-with-Like Bet365 CLV (Taken Odds vs Bet365 Closing Odds, N = 32,106):
   - Mean CLV                 : +0.27% (95% CI: [+0.17%, +0.37%])
   - % Beating Bet365 Close   : 40.82% (95% CI: [40.26%, 41.35%])

B. Pinnacle De-Vigged Closing Value (Taken Odds vs Pinnacle Fair Close, N = 59,487):
   - Mean Pinnacle CLV        : -5.84% (95% CI: [-5.90%, -5.76%])
   - % Beating Pinnacle Close : 21.64% (95% CI: [21.32%, 21.97%])

3. PROBABILITY CALIBRATION & HIGH CONFIDENCE BINS (RAW VS CALIBRATED)
------------------------------------------------------------------------------------------
Expected Calibration Error (ECE): Raw = 0.0113 | Calibrated = 0.0068
Bin        | Count    | Raw Pred     | Cal Pred     | Empirical Freq   | Raw Err    | Cal Err   
------------------------------------------------------------------------------------------
0.0-0.1    | 2662     | 0.0664       | 0.0672       | 0.0920           | 0.0256     | 0.0216    
0.1-0.2    | 8673     | 0.1573       | 0.1585       | 0.1683           | 0.0110     | 0.0000    
0.2-0.3    | 21108    | 0.2539       | 0.2568       | 0.2620           | 0.0082     | 0.0014    
0.3-0.4    | 10372    | 0.3416       | 0.3408       | 0.3294           | 0.0121     | 0.0126    
0.4-0.5    | 6477     | 0.4477       | 0.4467       | 0.4471           | 0.0005     | 0.0114    
0.5-0.6    | 4602     | 0.5464       | 0.5458       | 0.5261           | 0.0203     | 0.0074    
0.6-0.7    | 2972     | 0.6457       | 0.6454       | 0.6386           | 0.0071     | 0.0177    
0.7-0.8    | 1694     | 0.7443       | 0.7440       | 0.7090           | 0.0354     | 0.0099    
0.8-0.9    | 770      | 0.8405       | 0.8380       | 0.8078           | 0.0327     | 0.0059    
0.9-1.0    | 157      | 0.9269       | 0.9260       | 0.8790           | 0.0479     | 0.0453    

4. EDGE DISTRIBUTION AUDIT & SUSPECTED MODEL ERRORS
------------------------------------------------------------------------------------------
A. Breakdown by Outcome:
   Outcome  | Count    | % Bets     | Mean Edge    | Win Rate   | ROI (%)   
   H        | 19829    |   33.3%    |    -4.18%   |  44.16%   |  -6.03%
   D        | 19829    |   33.3%    |    -4.57%   |  25.13%   |  -4.83%
   A        | 19829    |   33.3%    |    -1.68%   |  30.70%   |  -7.65%

B. Breakdown by Odds Bucket:
   Bucket     | Count    | % Bets     | Mean Edge    | Win Rate   | ROI (%)   
   1.0-1.5    | 4043     |    6.8%    |    -7.50%   |  75.66%   |  -2.07%
   1.5-2.0    | 6856     |   11.5%    |    -6.97%   |  56.77%   |  -2.78%
   2.0-3.0    | 11564    |   19.4%    |    -4.58%   |  39.38%   |  -6.20%
   3.0-5.0    | 26574    |   44.7%    |    -4.31%   |  26.29%   |  -5.56%
   5.0+       | 10450    |   17.6%    |     3.71%   |  12.80%   | -11.50%

C. Suspected Model Errors (Edge > 10%):
   - Count of Bets > 10% Edge  : 11,182 (18.80% of all bet opportunities)
   - Breakdown by Selection    : {'A': 5138, 'H': 3569, 'D': 2475}
   - Win Rate of >10% Edge Bets: 25.19% (ROI: -9.36%)
   - Diagnosis                 : High-edge flags in domestic soccer are overwhelmingly model
                                 artifacts (e.g. over-projected draw probabilities or longshots).

5. FLAT-STAKE PERFORMANCE ACROSS POSITIVE EV THRESHOLDS (MAX 1 BET PER MATCH)
------------------------------------------------------------------------------------------
Min Edge   | Bets     | Total Staked   | P/L (Flat)   | ROI (%)    | Avg Edge   | Pin CLV    | Win Rate  
------------------------------------------------------------------------------------------
2.0%       | 15578    | NGN 1,557,800.0 | NGN -116,679.0 |  -7.49%    |  20.71%   |  -5.64%   |  30.66%
3.0%       | 14705    | NGN 1,470,500.0 | NGN -113,757.0 |  -7.74%    |  21.79%   |  -5.70%   |  30.09%
5.0%       | 13048    | NGN 1,304,800.0 | NGN -111,607.0 |  -8.55%    |  24.05%   |  -5.84%   |  28.89%
8.0%       | 10933    | NGN 1,093,300.0 | NGN -99,688.0 |  -9.12%    |  27.45%   |  -5.96%   |  27.38%
10.0%      | 9616     | NGN 961,600.0  | NGN -87,616.0 |  -9.11%    |  29.98%   |  -5.99%   |  26.49%
==========================================================================================
SIGNAL CHECK: ROI DOES NOT rise with edge threshold. Higher edge does NOT equal higher profit.
              Edges > 8-10% represent Poisson distribution tail misestimation, not true alpha.
==========================================================================================
```

---
*Generated automatically by EdgeScout Phase 1 Diagnostic Suite.*
