# Binance Derivatives Calibration Study — Tasks

## Phase 0: Sample Construction
- [x] 0.1 Find Binance winners (137 found, 2x+ in 30d, MC $5M-$2B)
- [x] 0.2 Find control group (1 found — criteria too strict)
- [x] 0.3 Find losers (67 found, -50%+ drop)
- [x] 0.4 Save as binance_sample.json

## Phases 1-4: Data Collection (combined script)
- [x] 1-4. Collect spot klines, futures klines, funding rate, basis (T-60 to T+5)
- [x] Data: spot 173, futures 182, funding 187, basis 175 tokens
- [x] Saved to binance_derivatives_data.json

## Phase 5: OI Infrastructure (independent, forward-looking)
- [x] 5.1 Collect current 30d OI snapshots (544 tokens)
- [x] 5.2 Compute OI metrics (oi_mc_ratio, growth)
- [x] 5.3 Daily cron script: collect_oi_daily.py

## Phase 6: Analysis — Winners vs Losers
- [x] 6.1 Merge all collected data
- [x] 6.2 Discrimination ratios: basis (1.32), F/S ratio (0.84), TBR (0.99)
- [x] 6.3 Mann-Whitney U: basis p=0.005***, F/S ratio p=0.033*, funding p=0.28 (NS)
- [x] 6.4 Funding hypothesis: REJECTED — не дискриминирует (p=0.28)
- [x] 6.5 Interaction: funding × vol_growth p=0.044* — combo signal works

## Phase 7: MC/FDV Interaction
- [x] 7.1 MC: winners $67M vs losers $150M (p=0.000003)
- [x] 7.2 Concentration: low F/S + low MC = organic accumulation → pump potential

## Phase 8: Cluster Integration
- [x] 8.1 Multiplier segmentation: 3x+ = lowest F/S ratio (3.23)
- [x] 8.2 Vol decline before pump (0.86 vs 0.96) = B_gradual pattern

## Phase 9: Calibrated Thresholds
- [x] 9.1 3 new metrics: basis 30d, basis persistence, F/S ratio T-30
- [x] 9.2 Thresholds calibrated (see empirical_thresholds.yaml)
- [x] 9.3 empirical_thresholds.yaml updated
- [x] 9.4 binance_calibration_report.md written
- [x] 9.5 lessons_learned.md updated (Lesson #6)
- [x] 9.6 All 3 personas updated (CC: Screen H, CG: Derivatives scoring, G: Red flags 11-12)

## Key Findings Summary
1. **Basis** = strongest new signal (p=0.005). Futures discount before pump.
2. **F/S ratio** = significant at T-30 (p=0.033). Spot accumulation → pump.
3. **Funding** = NOT a signal (p=0.28). General market backdrop.
4. **TBR** = not actionable (0.5% difference).
5. **Absolute volumes** = not discriminating.
