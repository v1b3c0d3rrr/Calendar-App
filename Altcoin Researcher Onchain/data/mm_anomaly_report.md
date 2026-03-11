# Market Maker & Anomaly Detection Report

**Sample**: 211 tokens (61W vs 128L)
**Method**: Mann-Whitney U (two-sided), T-7→T vs T-14→T-7 comparison

## Significant Signals (p < 0.1)

| # | Feature | W median | L median | p-value | Effect | Direction |
|---|---------|---------|---------|---------|--------|-----------|
| 1 | whale_accumulation_ratio_signal | 0.3750 | 0.2857 | 0.0002 *** | -0.338 | W higher |
| 2 | sync_ratio | 0.5988 | 0.7112 | 0.0009 *** | 0.298 | L higher |
| 3 | burst_max_hourly | 22.0000 | 42.0000 | 0.0062 *** | 0.247 | L higher |
| 4 | new_addresses_in_signal | 58.0000 | 105.5000 | 0.0083 *** | 0.238 | L higher |
| 5 | burst_ratio | 4.4468 | 5.6667 | 0.0321 ** | 0.193 | L higher |
| 6 | whale_accum_delta | 0.0196 | -0.0345 | 0.0482 ** | -0.178 | W higher |

## Metric Categories

### Velocity (activity acceleration T-7→T vs T-14→T-7)
- `transfer_acceleration`: tx count ratio
- `volume_acceleration`: volume ratio
- `unique_addr_acceleration`: unique addresses ratio

### Coordination (burst & sync patterns)
- `burst_ratio`: max hourly / avg hourly rate
- `sync_ratio`: fraction of transfers within ±5 min of another
- `burst_acceleration`: signal burst / baseline burst

### Concentration (top-holder dynamics)
- `top10_share_*`: top-10 address volume share
- `concentration_delta`: change in top-10 share

### CEX-DEX Bridge (liquidity movement)
- `cex_withdrawal_accel`: CEX withdrawal volume acceleration
- `bridge_addr_*`: addresses touching both CEX and DEX
- `net_cex_flow_delta_pct`: change in net CEX flow direction

### Whale Behavior
- `whale_accumulation_ratio_*`: fraction of whales accumulating
- `whale_accum_delta`: change in accumulation ratio
- `new_whales`: new whale addresses in signal period

### Composite
- `smart_money_score`: weighted combination of CEX withdrawal + whale accum + activity