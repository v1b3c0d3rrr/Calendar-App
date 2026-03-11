# Кластерный анализ типов пампа — Отчёт

Дата: 2026-03-11
Data provided by CoinGecko (https://www.coingecko.com/en/api/)

## Методология

121 чистый winner (исключены DEX-токены, стейблы, tokenized stocks, fan tokens) кластеризован по типу price action до T-0 на основе:
- ATH drawdown (% от ATH)
- Accumulation duration (дни в ±20% range)
- Pre-trend 30d (% change)
- Volatility 30d

---

## 5 типов пампа

### A: Deep Recovery (35 токенов, median 2.2x)

**Паттерн**: Токен упал >70% от ATH, долго лежал на дне, потом резко развернулся.

| Характеристика | Значение |
|---------------|----------|
| ATH drawdown | median **-78%** |
| Accumulation | median 2 дня (быстрый разворот) |
| Pre-trend 30d | **-41%** (всё ещё падает до самого разворота) |
| Pump duration | 29 дней |
| MC at T-0 | $17.6M |

**Метрики на T-7:**
| Метрика | Median | P25 | P75 |
|---------|--------|-----|-----|
| Vol/MC | **3.86%** | 1.22% | 33.9% |
| Price 7d | **-12.3%** | -19.3% | -5.8% |
| Volatility | 10.3% | 5.3% | 13.2% |
| Avg Vol 7d | $715K | | |
| MC/FDV | 0.505 | 0.189 | |
| Supply ratio | 0.957 | 0.265 | |

**Ключевой signal**: Vol/MC 3.9% при ПРОДОЛЖАЮЩЕМСЯ падении цены (-12%). Кто-то accumulates на дне пока цена всё ещё красная. Это классический smart money pattern.

**Как ловить**: Vol/MC > 1.5% + ATH drawdown > -70% + цена всё ещё падает (price 7d < 0%) = accumulation on deep bottom.

---

### B: Gradual Accumulation (17 токенов, median 2.1x)

**Паттерн**: Умеренное падение -30-70% от ATH, длинная фаза accumulation (28 дней), потом рост.

| Характеристика | Значение |
|---------------|----------|
| ATH drawdown | median **-53%** |
| Accumulation | median **28 дней** (самый длинный) |
| Pre-trend 30d | **-16%** (медленное сползание) |
| Pump duration | 30 дней |
| MC at T-0 | $13.7M |

**Метрики на T-7:**
| Метрика | Median | P25 | P75 |
|---------|--------|-----|-----|
| Vol/MC | **3.07%** | 0.87% | 12.3% |
| Price 7d | **-0.1%** | -2.1% | +12.9% |
| Volatility | **4.6%** | 3.2% | 6.5% |
| Avg Vol 7d | $350K | | |
| MC/FDV | 0.253 | 0.064 | |
| Supply ratio | 0.462 | 0.155 | |

**Ключевой signal**: НИЗКАЯ волатильность (4.6% vs 10%+ у других) + стабильная цена (≈0% change) + low MC/FDV (0.25). Тишина перед штормом. Объём не аномальный, но scarcity (supply 46%) создаёт потенциал.

**Как ловить**: Volatility < 5% + price stable (±5%) + MC/FDV < 0.3 + accumulation > 14 дней = building position quietly.

---

### C: Breakout from Sideways (32 токена, median 2.2x)

**Паттерн**: Токен торгуется в range, не сильно далеко от ATH, потом пробивает вверх.

| Характеристика | Значение |
|---------------|----------|
| ATH drawdown | median **-27%** |
| Accumulation | median 10 дней |
| Pre-trend 30d | **-21%** (лёгкое сползание перед breakout) |
| Pump duration | 28 дней |
| MC at T-0 | $14.0M |

**Метрики на T-7:**
| Метрика | Median | P25 | P75 |
|---------|--------|-----|-----|
| Vol/MC | **1.08%** | 0.23% | 4.17% |
| Price 7d | **-0.4%** | -4.5% | +8.2% |
| Volatility | **5.4%** | 3.0% | 7.6% |
| Avg Vol 7d | $137K | | |
| MC/FDV | 0.322 | 0.114 | |
| Supply ratio | 0.646 | 0.365 | |

**Ключевой signal**: НИЗКИЙ Vol/MC (1.08%) — это самый тихий кластер. Breakout неожиданный. Сигнал — не volume, а proximity к ATH (drawdown -27%) + low volatility + low MC/FDV.

**Как ловить**: ATH drawdown < -40% + MC/FDV < 0.35 + volatility 3-8% + наличие катализатора. Volume signal слабый в этом кластере.

---

### D: Momentum Continuation (7 токенов, median 2.4x)

**Паттерн**: Токен уже растёт (near ATH, positive trend), рост продолжается.

| Характеристика | Значение |
|---------------|----------|
| ATH drawdown | median **-16%** |
| Accumulation | median 18 дней |
| Pre-trend 30d | **-5%** (практически flat/слегка вверх) |
| Pump duration | 29 дней |
| MC at T-0 | $19.0M |

**Метрики на T-7:**
| Метрика | Median | P25 | P75 |
|---------|--------|-----|-----|
| Vol/MC | **3.12%** | 2.8% | 6.2% |
| Price 7d | **-4.6%** | -5.9% | +13.5% |
| Volatility | **8.6%** | 8.3% | 11.4% |
| Avg Vol 7d | $103K | | |
| MC/FDV | 0.356 | 0.174 | |
| Vol trend | **1.62** | | |

**Ключевой signal**: РАСТУЩИЙ volume trend (1.62x — единственный кластер с >1.0). Объём НАРАСТАЕТ к T-0. Цена уже near ATH, momentum builds.

**Как ловить**: Vol trend > 1.3 + ATH drawdown > -30% + Vol/MC > 2%. Самый маленький кластер (7 штук) — редкий паттерн, но ORE (49x) здесь.

---

### E: V-Reversal (37 токенов, median 2.1x)

**Паттерн**: Резкое падение → резкий отскок. Высокая волатильность, минимальная accumulation.

| Характеристика | Значение |
|---------------|----------|
| ATH drawdown | median **-60%** |
| Accumulation | median **2 дня** (V-образный разворот) |
| Pre-trend 30d | **-44%** (быстрое падение) |
| Pump duration | 26 дней |
| MC at T-0 | $16.1M |

**Метрики на T-7:**
| Метрика | Median | P25 | P75 |
|---------|--------|-----|-----|
| Vol/MC | **16.4%** | 0.44% | 38.2% |
| Price 7d | **-5.2%** | -18.6% | +5.4% |
| Volatility | **11.9%** | 7.2% | 16.5% |
| Avg Vol 7d | **$4.8M** | | |
| MC/FDV | 0.316 | 0.183 | |
| Supply ratio | 0.66 | 0.27 | |

**Ключевой signal**: ЭКСТРЕМАЛЬНО высокий Vol/MC (16.4% — в 15x выше, чем C_breakout). Огромные объёмы ($4.8M median!) при микрокапе. Это capitulation + instant reversal. Biggest winners (ANDY70B 165x, 9BIT 11x, XPIN 11x) — все здесь.

**Как ловить**: Vol/MC > 5% + ATH drawdown -40 to -70% + high volatility > 10% + fast pre-drop (trend 30d < -30%) = capitulation bounce. Самый прибыльный паттерн, но и самый рискованный.

---

## Сводная таблица порогов по кластерам

| Метрика | A: Deep Recovery | B: Gradual Acc | C: Breakout | D: Momentum | E: V-Reversal |
|---------|-----------------|----------------|-------------|-------------|---------------|
| **N** | 35 | 17 | 32 | 7 | 37 |
| **Median mult** | 2.2x | 2.1x | 2.2x | 2.4x | 2.1x |
| **ATH dd** | -78% | -53% | -27% | -16% | -60% |
| **Acc days** | 2 | **28** | 10 | 18 | 2 |
| **Vol/MC T-7** | 3.9% | 3.1% | **1.1%** | 3.1% | **16.4%** |
| **Price 7d T-7** | **-12%** | ~0% | ~0% | -5% | **-5%** |
| **Volatility** | 10% | **4.6%** | 5.4% | 8.6% | **11.9%** |
| **MC/FDV** | 0.50 | **0.25** | 0.32 | 0.36 | 0.32 |
| **Supply ratio** | **0.96** | **0.46** | 0.65 | 0.86 | 0.66 |
| **Vol trend** | 0.76 | 0.67 | 0.90 | **1.62** | 0.94 |
| **Best signal** | Volume при падающей цене | Тишина + scarcity | Proximity ATH + low MC/FDV | Растущий объём | Extreme volume + high vol |

## Implications for scoring

Единый набор порогов не работает для всех типов. Нужно сначала определить тип ситуации, потом применять правильные пороги:

1. **Сначала classify**: по ATH drawdown + accumulation days + trend определяем кластер
2. **Потом score**: для каждого кластера свои критические метрики

Это объясняет, почему общий backtest давал только 65% — одни и те же пороги не подходят для breakout (low volume) и V-reversal (extreme volume).
