# Onchain Signal Discovery: Address Labeling + Transfer Collection

## Goal
Collect token transfers for T-14 to T (peak/bottom date) for 295 EVM tokens.
Label addresses (CEX, DEX, whale, etc.) to find onchain patterns that discriminate winners vs losers.

## Phase 1: Address Label Database
- [x] Download etherscan-labels (brianleect/etherscan-labels) — static JSON for ETH, BSC, Polygon, Arbitrum
- [x] Download CEX hot wallet list (tradezon/cex-list or manual curated list)
- [x] Hardcode DEX router/factory addresses (Uniswap V2/V3, PancakeSwap V2/V3, SushiSwap)
- [x] Build unified label lookup: address → {entity, type, chain}
- [x] Test label lookup on known addresses

## Phase 2: Transfer Collection
- [x] For each EVM token: compute T-14 and T-7 block numbers via Etherscan block-by-timestamp
- [x] Collect all ERC-20 transfers in [T-14, T] window
- [x] Store transfers in JSON per token (from, to, value, block, timestamp)
- [x] Handle pagination (>10k transfers), rate limits, free-chain restrictions
- [x] Progress tracking for resumable runs
- [x] **V1 DONE**: 197/295 collected (ETH only), BSC skipped (paid API)
- [ ] **V2 IN PROGRESS**: Recollecting ALL with correct T=start_date (NOT peak)
  - T=start_date (начало роста/падения), NOT peak/bottom
  - Window: T-14→T+7 (baseline + signal + confirmation)
  - ETH: Etherscan v2 API (free)
  - BSC: PublicNode/NodeReal RPC (free, eth_getLogs)

## Phase 3: Address Labeling & Enrichment
- [x] Label all addresses in collected transfers using LabelDB (44,945 labels)
- [x] Heuristic labeling: DEX pools (balanced flow), CEX-like (high tx+counterparties), whales (>5% volume)
- [x] Label coverage: 2.6% → 16.1% with heuristics
- [ ] WalletLabels.xyz API fallback for top addresses (deferred)

## Phase 4: Signal Analysis (PRELIMINARY — 92 tokens)
- [x] 70/15/15 stratified train/val/test split
- [x] Mann-Whitney U tests + effect sizes
- [x] Threshold calibration on train, validation on val/test
- [x] **KEY FINDING**: delta_transfer_count (p=0.034) — Winners +206% vs Losers +16% (12.6x ratio)
- [x] **KEY FINDING**: transfer_intensity (p=0.035) — Winners 3.06x vs Losers 1.16x
- [x] Report: data/onchain_signal_report.md
- [ ] Re-run when >150 tokens collected for final results

---

## Phase 5: Holder Snapshots (Genesis → T, каждые 12ч)

### Цель
Собрать ВСЕ трансферы от первого трансфера токена до T (пик/дно).
Построить снэпшоты держателей каждые 12 часов.
Анализировать структуру и динамику держателей как сигнал winners vs losers.

### 5.1: Коллектор снэпшотов
- [x] Скрипт `collect_holder_snapshots.py`:
  - Собирает все ERC-20 трансферы от блока 0 до блока T
  - Строит running balance map (address → balance) хронологически
  - Каждые 12ч (по timestamp) фиксирует снэпшот
  - Рекурсивная разбивка блоков при >10k трансферов (Etherscan лимит)
  - Двойной API key (KEY_1 free chains, KEY_2 BSC)
- [x] Формат снэпшота на каждые 12ч:
  - total_holders, top10/20/50/100 concentration, gini, hhi
  - new_holders, exited_holders, whale_count
  - median/mean/max holding, transfers_count, volume
- [x] Сохранение: `data/snapshots/{coin_id}.json`
- [x] Progress tracking: `data/snapshot_progress.json`
- [ ] **IN PROGRESS**: Тестовый прогон — SIERRA (124tx), VATRENI (2598tx) OK
- [ ] Полный сбор 295 токенов

### 5.2: Анализ динамики держателей
- [x] Скрипт `analyze_holder_dynamics.py`:
  - Загружает все снэпшоты, вычисляет производные метрики
  - holder_growth_rate, concentration_trend, whale_accumulation
  - churn_rate, new_holder_acceleration, vol/transfer acceleration
  - Mann-Whitney U тесты winners vs losers
- [x] Предварительный запуск на 64 токенах (46W vs 18L)
- [x] **KEY FINDING**: Net holders T-7 — Winners +4 vs Losers +0.5 (8x, p=0.002)
- [x] **KEY FINDING**: New holders T-7 — Winners 12.5 vs Losers 4.0 (3.1x, p=0.043)
- [x] **KEY FINDING**: Churn rate T-7 — Winners 0.33 vs Losers 0.83 (p=0.041)
- [x] Калибрационный отчёт: `data/holder_dynamics_report.md`
- [ ] Re-run когда >100 токенов для финальных результатов

### 5.3: Интеграция с существующими сигналами
- [ ] Объединить holder signals с Vol/MC, MC/FDV, basis и другими
- [ ] Обновить empirical_thresholds.yaml
- [ ] Обновить персоны в Alt Boss

---

## Phase 6: Market Maker & Wallet Clustering Analysis

### Цель
Обнаружить маркет-мейкеров (MMs), кластеризовать связанные адреса и найти аномальные паттерны
за неделю до пампа. MMs работают с десятков адресов — нужно видеть полную картину.

### 6.1: MM Labeling (DONE)
- [x] Hardcoded MM wallets: Wintermute, DWF Labs, Jump Trading, GSR, Cumberland, Amber, Alameda, Auros, Folkvang
- [x] MM_ENTITIES set для etherscan-labels matching
- [x] `_classify_entity()` обновлён: market_maker type
- [x] `_load_mm_wallets()` в LabelDB
- [x] Тест: 219 market_maker labels, DB = 45,096 total

### 6.2: Address Clustering (V2 — DONE, ETH+BSC)
- [x] Скрипт `cluster_addresses.py` обновлён для сканирования всех transfer файлов
- [x] 234 токена (62W vs 129L), T=start_date
- [x] **KEY FINDING**: cluster_retail_signal_n_addresses p=0.0011 — W=153 vs L=353 (losers 2.3x больше retail)
- [x] **KEY FINDING**: new_addr_count p=0.0072 — W=56 vs L=102 (losers привлекают 1.8x больше новых адресов)
- [x] Report: `data/cluster_analysis_report.md`

### 6.3: Anomaly Detection (V2 — ETH only, V3 pending with BSC)
- [x] Скрипт `detect_mm_anomalies.py` — 211 токенов (61W vs 128L), T=start_date
- [x] Обновлён для сканирования всех transfer файлов (ETH+BSC)
- [x] **KEY FINDING**: whale_accumulation_ratio (p=0.0002!!!) — W 37.5% vs L 28.6%
- [x] **KEY FINDING**: sync_ratio (p=0.0009) — W 0.60 vs L 0.71 (losers more coordinated)
- [x] **KEY FINDING**: burst_max_hourly (p=0.006) — W 22 vs L 42 (losers pump harder)
- [x] **KEY FINDING**: new_addresses_in_signal (p=0.008) — W 58 vs L 105 (losers attract more new addrs)
- [x] **KEY FINDING**: burst_ratio (p=0.032) — W 4.45 vs L 5.67
- [x] **KEY FINDING**: whale_accum_delta (p=0.048) — W +0.02 vs L -0.03
- [x] CRITICAL FIX: T was peak_date, now start_date → completely different results!
- [ ] **V3 PENDING**: Re-run with full ETH+BSC dataset (~245 tokens)

### 6.4: CEX Flow Analysis (V2 — DONE)
- [x] Скрипт `analyze_cex_flows.py` — 228 токенов (62W vs 128L)
- [x] **KEY FINDING**: sp_unique_depositors p=0.0026 — W=26, L=52 (losers 2x больше депозиторов)
- [x] **KEY FINDING**: sp_deposit_count p=0.0085 — W=48, L=132 (losers 2.75x больше депозитов)
- [x] **KEY FINDING**: sp_withdrawal_count p=0.04 — W=137, L=174
- [x] Report: `data/cex_flow_report.md`

### 6.5: Known Manipulator Analysis (DONE — all 4 phases)
- [x] River PUMP: top suspect `0x9642b23...` score=9, 15.4% vol, 432 tx, funds 41 addrs
- [x] Folks PUMP: top suspect `0x2052bf1...` score=5, 19.9% vol, accum→dump
- [x] River DUMP: same `0x9642b23...` confirmed (23.2% vol), new puppet master funds **614 addrs**
- [x] Folks DUMP: same `0x2052bf1...` confirmed (22.8% vol, score=6), funds 45 addrs
- [x] Кросс-фазовый паттерн: 0 CEX, pure DEX, 11-14% avg vol share, puppet networks 41-614 addrs
- [x] Report: `data/manipulator_analysis/manipulator_analysis.json`

### 6.6: BSC Transfer Collection (IN PROGRESS)
- [x] Скрипт `collect_bsc_transfers.py` с NodeReal RPC (archive support)
- [x] 120/141 BSC токенов собрано
- [ ] COAI (ChainOpera AI) — collection in progress
- [ ] Финализация после завершения сбора

### 6.7: Финальный pipeline (PENDING)
- [ ] Re-run anomaly detection (V3) на полном ETH+BSC датасете (~245 токенов)
- [ ] Re-run cluster analysis на полном датасете
- [ ] Интеграция manipulator patterns как features
- [ ] Обновить empirical_thresholds.yaml
- [ ] Финальный combined report
