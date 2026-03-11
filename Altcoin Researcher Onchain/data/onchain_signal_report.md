# Onchain Signal Discovery Report

## Dataset
- Total tokens: 175
- Train: 121 (40W / 81L)
- Val: 25 (8W / 17L)
- Test: 29 (10W / 19L)

## Feature Ranking (by p-value on training set)

| Feature | W mean | L mean | Ratio | p-value | Effect |
|---------|--------|--------|-------|---------|--------|
| sp_dex_volume_pct | 1.48 | 2.84 | 0.52x | 0.0923 | 0.189 |
| delta_whale_volume | 16.44 | 29.17 | 0.56x | 0.2406 | 0.132 |
| delta_dex_volume | 200.27 | 161.50 | 1.24x | 0.2667 | 0.176 |
| dex_shift | -0.74 | -0.34 | 2.20x | 0.3281 | 0.110 |
| delta_cex_inflow | 29.36 | -6.56 | -4.48x | 0.4116 | 0.134 |
| delta_transfer_count | 171.25 | 121.23 | 1.41x | 0.4227 | 0.090 |
| transfer_intensity | 2.71 | 2.21 | 1.23x | 0.4227 | 0.090 |
| sp_cex_net_flow_pct | -0.14 | -0.21 | 0.69x | 0.5032 | 0.075 |
| sp_transfer_count | 1888.12 | 1203.33 | 1.57x | 0.5120 | 0.073 |
| whale_shift | -1.88 | -1.10 | 1.70x | 0.5481 | 0.067 |
| sp_whale_volume_pct | 56.58 | 54.34 | 1.04x | 0.5816 | 0.062 |
| delta_cex_net_flow | 28.33 | -126.11 | -0.23x | 0.6397 | 0.070 |
| delta_unique_addresses | 87.76 | 627.51 | 0.14x | 0.6435 | 0.052 |
| address_growth | 1.88 | 7.28 | 0.26x | 0.6435 | 0.052 |
| sp_unique_addresses | 370.12 | 508.53 | 0.73x | 0.7808 | 0.031 |
| delta_cex_outflow | 27.61 | 119.80 | 0.23x | 0.8658 | 0.026 |
| sp_cex_outflow_pct | 9.29 | 7.24 | 1.28x | 0.9648 | 0.005 |
| cex_flow_shift | 1.70 | 0.22 | 7.65x | 0.9736 | 0.004 |
| sp_cex_inflow_pct | 9.14 | 7.03 | 1.30x | 0.9824 | 0.003 |
| sp_bridge_volume_pct | 0.32 | 1.55 | 0.21x | 0.9868 | 0.002 |

## Calibrated Thresholds

### sp_dex_volume_pct
- Direction: < 1.56
- Train F1: 0.541
- Val: F1=0.5, P=0.35, R=0.875, Acc=0.44
- Test: F1=0.571, P=0.444, R=0.8, Acc=0.586

## Key Findings

### Strongest Discriminators (p < 0.05)
