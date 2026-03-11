# CEX Flow Analysis (Rotation-Filtered)

**Dataset**: 228 tokens (62W / 128L)
**Rotation filtered**: 966786 transfers removed

## Feature Ranking (by p-value)

| Feature | W mean | L mean | W median | L median | p-value | Effect | Sig |
|---------|--------|--------|----------|----------|---------|--------|-----|
| sp_unique_depositors | 52.85 | 121.80 | 26.00 | 52.00 | 0.0026 | 0.269 | ** |
| sp_deposit_count | 115.95 | 217.08 | 48.00 | 132.00 | 0.0085 | 0.236 | ** |
| sp_withdrawal_count | 301.69 | 432.03 | 137.00 | 174.00 | 0.0398 | 0.184 | * |
| sp_withdrawal_avg_size | 43292200.63 | 625793366.86 | 2457.41 | 10573.16 | 0.0538 | 0.173 | ~ |
| sp_deposit_pct | 8.53 | 10.65 | 7.93 | 11.04 | 0.0623 | 0.167 | ~ |
| sp_unique_withdrawers | 163.95 | 178.94 | 47.00 | 68.00 | 0.0772 | 0.158 | ~ |
| sp_deposit_avg_size | 58841185.57 | 1598962517.96 | 8319.66 | 18813.04 | 0.0775 | 0.158 | ~ |
| sp_withdrawal_pct | 8.84 | 9.96 | 8.84 | 9.56 | 0.1217 | 0.139 |  |
| sp_rotation_pct | 20.06 | 23.44 | 13.57 | 17.59 | 0.2055 | 0.113 |  |
| delta_unique_depositors | 343.24 | 167.82 | 66.70 | 86.70 | 0.2196 | 0.130 |  |
| delta_deposit_count | 655.94 | 216.05 | 62.50 | 93.00 | 0.2347 | 0.126 |  |
| deposit_intensity | 7.56 | 3.16 | 1.63 | 1.93 | 0.2347 | 0.126 |  |
| sp_whale_withdrawal_pct | 2.27 | 3.16 | 0.00 | 1.01 | 0.3702 | 0.080 |  |
| sp_whale_deposit_pct | 4.14 | 3.91 | 0.00 | 1.41 | 0.4275 | 0.071 |  |
| delta_deposit_pct | 4.81 | 170.08 | -25.40 | -12.70 | 0.5966 | 0.056 |  |
| delta_net_flow_pct | 7551.44 | -83.40 | -47.20 | -48.50 | 0.6614 | 0.045 |  |
| sp_net_flow_pct | -0.31 | 0.68 | 0.00 | 0.00 | 0.7293 | 0.031 |  |
| delta_unique_withdrawers | 1105.69 | 617.01 | 92.10 | 97.30 | 0.7423 | 0.034 |  |
| delta_withdrawal_pct | 2379.01 | 182.63 | -8.60 | 4.00 | 0.7995 | 0.026 |  |
| sp_deposit_withdrawal_ratio | 2.25 | 1.33 | 1.06 | 1.00 | 0.8737 | 0.017 |  |
| delta_withdrawal_count | 1255.14 | 375.84 | 120.80 | 127.60 | 0.9388 | 0.008 |  |
| withdrawal_intensity | 13.55 | 4.76 | 2.21 | 2.28 | 0.9388 | 0.008 |  |

## Key Findings

- **sp_unique_depositors**: Winners lower (52.85 vs 121.80, p=0.0026)
- **sp_deposit_count**: Winners lower (115.95 vs 217.08, p=0.0085)
- **sp_withdrawal_count**: Winners lower (301.69 vs 432.03, p=0.0398)
- **sp_withdrawal_avg_size**: Winners lower (43292200.63 vs 625793366.86, p=0.0538)
- **sp_deposit_pct**: Winners lower (8.53 vs 10.65, p=0.0623)
- **sp_unique_withdrawers**: Winners lower (163.95 vs 178.94, p=0.0772)
- **sp_deposit_avg_size**: Winners lower (58841185.57 vs 1598962517.96, p=0.0775)