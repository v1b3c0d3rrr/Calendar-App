# Калибровка деривативных метрик Binance

Дата: 2026-03-11
Выборка: 137 winners (2x+ за 30d) vs 67 losers (-50%+ за 30d), все на Binance спот+фьючерсы

## Ключевые находки

### 1. Basis (фьючерс-спот спрэд) — СИЛЬНЕЙШИЙ новый сигнал (p=0.005)

Winners перед пампом торгуются с **бОльшим дисконтом** на фьючерсах:
- Winners basis 30d: **-0.078%** (фьючерсы дешевле спота)
- Losers basis 30d: **-0.059%**
- Winners basis persistence (доля дней с премией): **6.7%** vs Losers **10%**

**Интерпретация**: Перед пампом фьючерсный рынок ПЕССИМИСТИЧЕН — шортисты давят цену ниже спота. Это создаёт:
1. Накопление short OI → топливо для squeeze
2. Smart money покупает на споте (ниже фьючерсного рынка)
3. Divergence spot > futures = leading indicator

**Порог**: Basis < -0.06% (30d avg) = bullish divergence. Basis > -0.03% = нейтрально.

### 2. Futures/Spot Vol Ratio на T-30 (p=0.033)

Winners имеют **НИЖЕ** leverage ratio ЗА МЕСЯЦ до пампа:
- Winners: **3.48** (на T-30)
- Losers: **4.15**

**Интерпретация**: Спотовое накопление (lower leverage) предшествует реальным пампам. Высокий leverage ratio = спекулятивный bubble, который чаще лопается.

**Нюанс**: на T-7 (ближе к пампу) разница исчезает (3.64 vs 3.30, p=0.97). Значит leverage подключается уже ПОСЛЕ начала движения.

**Порог**: F/S ratio < 3.5 (на T-30) = spot-driven accumulation. > 5.0 = leverage-heavy = red flag.

### 3. Market Cap — сильнейший дискриминатор (p=0.000003)

- Winners median MC: **$67M**
- Losers median MC: **$150M**

Подтверждает: мелкие токены на Binance пампятся, крупные — чаще падают. Это не новый сигнал, но ПОДТВЕРЖДЕНИЕ из другой выборки.

### 4. Spot Vol Growth (p=0.063, borderline)

Winners показывают **снижение** объёма перед пампом:
- Winners vol T-7 / vol T-30: **0.86** (объём упал на 14%)
- Losers: **0.96** (объём стабилен)

**Интерпретация**: "Тишина перед штормом" — снижение объёма перед пампом = период тихого накопления. Совпадает с кластером B_gradual_accumulation из предыдущей калибровки.

## Что НЕ работает (опровергнутые гипотезы)

### Фандинг — НЕ дискриминирует (p=0.28-0.84)

| Метрика | Winners | Losers | p-value |
|---------|---------|--------|---------|
| Persistence 30d | 0.794 | 0.833 | 0.277 |
| Avg 30d | 0.002% | 0.004% | 0.837 |
| Annualized | 2.2% | 3.9% | 0.835 |
| Max 30d | 0.005% | 0.005% | 0.210 |

**Вывод**: Положительный фандинг — это ОБЩИЙ ФОН рынка, а не специфический сигнал для отдельных токенов. И winners, и losers имеют ~80% persistence с положительным фандингом. Гипотеза "2 месяца повышенного фандинга = short squeeze" НЕ подтверждена.

Однако: funding × vol_growth INTERACTION значим (p=0.044). Winners имеют НИЖЕ interaction score (0.65 vs 0.74), что означает: среди токенов с высоким фандингом, те что снижают объём — чаще пампятся.

### Taker Buy Ratio — практически бесполезен

Winners: 0.488, Losers: 0.493. Разница 0.5% — не actionable. Только 4% winners имеют TBR > 0.52.

### Абсолютные объёмы (spot и futures) — НЕ дискриминируют

Spot и futures volume в абсолютных величинах не различают winners от losers (p > 0.15). Это подтверждает: важен не абсолютный объём, а его СТРУКТУРА (spot vs futures, рост/падение).

### Futures/Spot Ratio на T-7 — НЕ дискриминирует (p=0.97)

К моменту T-7 leverage ratio одинаков. Различия существуют только на T-30.

## MC × Funding по сегментам

| Сегмент | Winners persist | Losers persist |
|---------|----------------|----------------|
| Micro <$50M | 0.828 (n=54) | 0.911 (n=7) |
| Small $50-300M | 0.778 (n=51) | 0.889 (n=35) |
| Mid+ >$300M | 0.667 (n=15) | 0.778 (n=25) |

Тренд: losers ВСЕГДА имеют чуть выше funding persistence. Для mid-cap (>$300M) разница наибольшая.

## Мультипликатор и деривативы

| Mult | Funding persist | F/S ratio | Taker Buy |
|------|----------------|-----------|-----------|
| 2-2.5x (n=127) | 0.789 | 3.60 | 0.487 |
| 2.5-3x (n=4) | 0.850 | 5.90 | 0.501 |
| 3x+ (n=6) | 0.783 | 3.23 | 0.492 |

Наблюдение: 3x+ winners имеют НИЖЕ F/S ratio (3.23 vs 3.60) — подтверждает, что самые сильные пампы = spot-driven.

## Калиброванные пороги (ФИНАЛЬНЫЕ)

| Метрика | Buy Zone | Neutral | Avoid | Значимость |
|---------|----------|---------|-------|------------|
| **Basis 30d avg** | < -0.08% | -0.06% to -0.03% | > -0.03% | p=0.005 *** |
| **Basis 7d avg** | < -0.10% | -0.06% to -0.03% | > -0.03% | p=0.019 * |
| **Basis persistence** | < 10% | 10-20% | > 20% | p=0.048 * |
| **F/S ratio (T-30)** | < 3.0 | 3.0-5.0 | > 5.0 | p=0.033 * |
| **MC** | < $100M | $100-300M | > $300M | p=0.000003 *** |
| Spot vol growth | < 0.85 | 0.85-1.0 | > 1.0 | p=0.063 (borderline) |
| Funding persist × vol_growth | < 0.65 | 0.65-0.80 | > 0.80 | p=0.044 * |

## Рекомендации для персон

### CC (Cluster Analyst)
- Добавить **Basis Score** как новый Screen (Screen H: Futures Discount):
  - Basis 30d < -0.08% = +5 к скору (фьючерсы пессимистичны = squeeze potential)
  - F/S ratio < 3.0 на T-30 = +3 (spot accumulation)
- Volume decline перед пампом (vol_growth < 0.85) = подтверждает кластер B_gradual
- 3x+ winners = spot-driven → при скоринге бонус за low F/S ratio

### CG (Evidence Analyst)
- В Derivatives dimension (вес 0.10):
  - Basis < -0.08%: +2 балла
  - Basis persistence < 10%: +1
  - F/S ratio < 3.0: +1
  - F/S ratio > 5.0: -1 (leverage red flag)
- НЕ использовать: funding rate, taker buy ratio, абсолютные объёмы
- Gate check: F/S ratio > 8.0 = IGNORE (extreme leverage = casino)
- Кросс-проверка: spot volume decline + futures discount = strong entry setup

### G (Due Diligence)
- F/S ratio > 5.0 = RED FLAG #11: Leverage-driven pricing, высокий риск liquidation cascade
- Basis persistence > 30% в сочетании с высоким OI = crowded long positioning → dump risk
- MC confirmation: winners median $67M → sweet spot для 2x = small-cap на Binance
- **Concentration → pump hypothesis**: Low MC/FDV + low F/S ratio = organic accumulation ≠ leverage bubble. Высокая концентрация (top-10 > 60%) + low F/S ratio = whale accumulation, потенциал для pump. НО: если top-10 > 60% + HIGH F/S ratio → insider + leverage = extreme dump risk.
