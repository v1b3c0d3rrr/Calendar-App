# Address Clustering & Market Maker Analysis Report

**Tokens analyzed**: 234 (62W vs 129L)

## Summary Statistics

| Metric | Winners (median) | Losers (median) |
|--------|-----------------|-----------------|
| n_mm_heuristic | 0.0 | 0.0 |
| n_funding_clusters | 2.5 | 4.0 |
| n_temporal_clusters | 1.0 | 1.0 |

## Significant Signals (p < 0.1)

| Feature | W median | L median | p-value | Effect |
|---------|---------|---------|---------|--------|
| cluster_retail_signal_n_addresses | 153.50 | 353.50 | 0.0011 | 0.279 |
| new_addr_count | 56.50 | 102.00 | 0.0072 | 0.240 |

## Methodology

1. **Funding clusters**: addresses with common funding parent grouped together
2. **Temporal clusters**: addresses acting within ±5 min windows on 3+ occasions
3. **Heuristic MM**: addresses interacting with both CEX and DEX, 10+ total tx
4. **Anomaly detection**: signal (T-7→T) vs baseline (T-14→T-7) ratios
5. **Statistical test**: Mann-Whitney U (two-sided)