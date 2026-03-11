# Holder Dynamics Analysis Report

**Total tokens**: 82 (winners: 48, losers: 34)
**With leading data (S-7→S)**: 46W + 34L

## LEADING Metrics (S-7 → S) — BEFORE price movement

These are actionable: measured in the week BEFORE the token starts moving.
S = start_date = moment price begins rising (winners) or falling (losers).

| Metric | Winners (med) | Losers (med) | P-value | Signal |
|--------|:---:|:---:|:---:|:---:|
| Net holders S-7→S | 1.0000 | 5.0000 | 0.5592 | - |
| New holders S-7→S | 8.0000 | 18.5000 | 0.0617 | * |
| Exited holders S-7→S | 3.5000 | 11.0000 | 0.0198 | ** |
| Churn rate S-7→S | 0.3314 | 0.5267 | 0.1525 | - |
| Gini change S-7→S | 0.0000 | 0.0000 | 0.9534 | - |
| Top10% change S-7→S | 0.0000 | 0.0000 | 0.4804 | - |
| Whale change S-7→S | 0.0000 | 0.0000 | 0.7852 | - |
| Transfers S-7→S | 85.5000 | 144.0000 | 0.1625 | - |
| Volume S-7→S | 58814621165660483354624.0000 | 2010360635088812654985216.0000 | 0.0680 | * |
| New holder accel (vs S-14→S-7) | 0.8178 | 1.0357 | 0.1955 | - |
| Transfer accel (vs S-14→S-7) | 0.9344 | 1.0153 | 0.3706 | - |
| Volume accel (vs S-14→S-7) | 0.8032 | 0.8955 | 0.8686 | - |
| Total holders at S | 264.5000 | 580.5000 | 0.3000 | - |

## LAGGING Metrics (T-7 → T) — DURING price movement (NOT actionable)

These reflect holder behavior DURING the pump/dump. Informative but NOT predictive.

| Metric | Winners (med) | Losers (med) | P-value | Signal |
|--------|:---:|:---:|:---:|:---:|
| Net holders T-7→T | 5.0000 | 1.0000 | 0.0057 | *** |
| New holders T-7→T | 13.5000 | 8.5000 | 0.3840 | - |
| Churn rate T-7→T | 0.3529 | 0.8313 | 0.0007 | *** |
| Gini change T-7→T | 0.0000 | 0.0000 | 0.4347 | - |
| Whale change T-7→T | 0.0000 | 0.0000 | 0.4600 | - |

## Key Findings

### Actionable LEADING signals (p < 0.05, S-7→S window):
- **Exited holders S-7→S**: W=3.5000 vs L=11.0000 (ratio 0.32x, p=0.0198)

---
Raw data: `data/holder_dynamics.json` (82 tokens)