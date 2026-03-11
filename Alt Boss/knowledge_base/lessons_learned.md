# Accumulated Lessons — База знаний из ревью

Этот файл накапливает инсайты из каждого /review. Используется при будущих дискуссиях для улучшения качества решений.

---

## Lesson #1: Lagging vs Leading indicators для входа (2026-03-10)

**Контекст**: Общая стратегия входа/выхода.

**Инсайт**: Факторы подтверждения (запуск продукта, рост объёма за 24-48ч, пост-листинг стабилизация) — это **lagging indicators**. Если ждать их подтверждения для входа, цена уже улетит. Эти факторы:

- **НЕ подходят для тайминга входа** — к моменту подтверждения основной move уже сделан
- **Подходят для удержания/выхода** — подтверждают или опровергают тезис после входа

**Для входа использовать leading indicators**:
- Накопление (ончейн: рост уникальных холдеров, whale accumulation)
- Приближающийся датированный катализатор (до события, а не после)
- Нарративный momentum в ранней фазе (KOL начинают говорить, но массы ещё нет)
- Техническая структура: consolidation/accumulation pattern перед движением
- Рост dev activity / коммитов до запуска

**Для выхода/удержания использовать lagging confirmation**:
- Объём после катализатора: если не пришёл за 24-48ч → выходить
- Продукт запущен, но метрики (TVL, users, txns) не растут → выходить
- Post-event dump без recovery → тезис сломан

**Вывод для скоринга**: При оценке entry timing, высокий скор за "подтверждённые" факторы не должен перевешивать. Лучше войти раньше с меньшей уверенностью и управлять риском через стоп, чем ждать 100% подтверждения и купить на +50%.

**Разделение ответственности команд**:
- `/research` = решение о входе → ТОЛЬКО leading indicators
- `/review buy` = решение hold/exit → lagging confirmation УМЕСТНЫ и НУЖНЫ
- Модератор ОБЯЗАН challenge любого исследователя, который в `/research` требует lagging confirmation для входа

---

## Lesson #2: Эмпирическая калибровка скоринга (2026-03-11)

**Контекст**: Калибровочное исследование 17 winners vs 4 control vs 5 losers (MC <$30M, 6 мес lookback).

**Ключевые находки**:

### Volume/MC ratio — сильнейший leading indicator
- Winners median: **5.4%** на T-7 (7 дней до роста)
- Losers median: **0.76%** — в 7x ниже
- Control median: **0.11%** — в 50x ниже
- **Вывод**: Повышенный Vol/MC = кто-то accumulates ДО роста цены. Это настоящий leading indicator.
- **Порог**: Vol/MC > 3% = сильный сигнал (ранее использовали 5%, занижает hit rate)

### MC/FDV ratio — ПЕРЕОСМЫСЛЕН
- Winners median: **0.156** (только 16% supply в обращении)
- Losers median: **0.738** (74% уже разблокировано)
- **РАНЕЕ**: MC/FDV < 30% = red flag (massive unlocks ahead)
- **ТЕПЕРЬ**: MC/FDV < 30% = **scarcity premium = BULLISH** для micro-cap
- Red flag ТОЛЬКО при combo: low MC/FDV + team unlock cliff <30 дней + top-10 concentration >60%
- **Вывод**: Низкий float при micro-cap = потенциал роста. Высокий float = нет scarcity.

### Supply ratio подтверждает MC/FDV
- Winners: 37% circulating, Losers: 98% circulating
- Токен с >80% supply в обращении = limited growth potential

### Price momentum 7d — ранний direction signal
- Winners: **+6.4%** на T-7 (уже растут за неделю до основного move)
- Losers: **-9.0%** (уже падают)
- Это НЕ post-factum — это ранний тренд за 7 дней до мувмента

### Нарративы имеют значение
- Winners: AI/AI Agents (24%), Solana ecosystem (35%), DeFi (35%)
- Losers: legacy VC portfolios (Alameda, Delphi)
- При прочих равных, горячий нарратив = бонус

### Что НЕ работает как дискриминатор
- GitHub presence: 59% winners vs 60% losers — не различает
- Dev activity (commits): почти нулевая для всех micro-cap — CoinGecko не обновляет
- Twitter followers: данные недоступны через CoinGecko API
- Telegram users: слабый signal (winners 7.4K vs losers 10.9K — losers даже больше!)

### Backtest результаты (без overfit)
- Scoring model (threshold=50): hit rate 65%, catastrophic FP 0%
- Hit rate ниже 70% target — из-за data quality (5/17 winners с Vol/MC ≈ 0 в CoinGecko)
- Safety > Coverage: лучше пропустить winner, чем купить loser

**Для скоринга**: Три фактора вместе (Vol/MC > 3% + MC/FDV < 0.3 + Price 7d > 0%) = 0 losers получают BUY при любом разумном threshold. Это **robust combo**, не overfit.

*Полный отчёт: `calibration/calibration_report.md`*

---

## Lesson #3: 5 типов пампа требуют разных порогов (2026-03-11)

**Контекст**: Кластеризация 121 winner (без DEX, стейблов) по типу price action до T-0.

**Инсайт**: Единый набор порогов не работает — 5 типов роста имеют принципиально разные сигналы:

1. **Deep Recovery** (35): Упал >70%, кто-то покупает на дне при падающей цене. Signal = Vol/MC 3.9% при negative price trend.
2. **Gradual Accumulation** (17): Тишина перед штормом. LOW volatility (4.6%), stable price, LOW MC/FDV (0.25). Volume signal слабый.
3. **Breakout from Sideways** (32): Близко к ATH (-27%), низкий volume (1.1%). Signal = proximity к ATH + scarcity, НЕ volume.
4. **Momentum Continuation** (7): Уже растёт. Единственный кластер с РАСТУЩИМ vol trend (1.62x). Редкий, но ORE 49x.
5. **V-Reversal** (37): Экстремальный Vol/MC 16.4% + capitulation. Biggest winners (ANDY70B 165x). Highest risk.

**Вывод для скоринга**: ПЕРВЫЙ ШАГ = classify ситуацию (по ATH drawdown + accumulation days + trend). ВТОРОЙ = применить пороги нужного кластера. Без классификации hit rate 65%; с ней должен быть выше.

**Ключевое переосмысление**: Volume — НЕ универсальный signal. Для B_gradual_accumulation и C_breakout volume не различает (1.1-3%). Там scarcity (MC/FDV < 0.3) и тишина (low volatility) важнее.

*Полный отчёт: `calibration/cluster_report.md`*

---

## Lesson #4: Social metrics из CoinGecko — слабый сигнал (2026-03-11)

**Контекст**: Попытка добавить social factors к скорингу. LunarCrush API требует платную подписку ($19+/мес). CoinGecko community data проанализированы для 121 winners.

**Ключевые находки**:

### Watchlist Portfolio Users — НЕ дискриминирует
- Все квартили по WL показывают одинаковый median multiplier (~2.1x)
- Между кластерами разброс всего 2.6x (1,501 для C_breakout vs 3,855 для D_momentum) — слабо
- **Вывод**: Популярность на CoinGecko НЕ предсказывает размер роста

### CoinGecko Sentiment — бесполезен
- Median sentiment_up = 100% для ВСЕХ кластеров
- Данные есть только у 50% токенов
- **Контринтуитивно**: низкий sentiment коррелирует с чуть БОЛЕЕ высоким multiplier (2.4x vs 2.1x)
- **Вывод**: Не использовать в скоринге

### Telegram presence — minor signal по кластерам
- B_gradual_accumulation: 94% имеют Telegram (highest)
- A_deep_recovery: 54% (lowest)
- Интерпретация: проекты с тихой аккумуляцией чаще имеют активное комьюнити
- **Вывод**: Telegram presence как дополнительный фильтр для B_gradual, но не основной

### GitHub — НЕ дискриминирует (подтверждено)
- D_momentum 42% vs A_deep_recovery 2% — разброс по типам, НЕ по качеству
- Commits за 4 недели: у большинства micro-cap = 0 (CoinGecko не обновляет)

### Что НУЖНО, но недоступно бесплатно
- Twitter follower GROWTH RATE (рост подписчиков за 7-30 дней до пампа)
- KOL calls / mentions (количество и качество mentions от influencers)
- Social volume spikes (LunarCrush Galaxy Score, AltRank — платный API)
- Sentiment trajectory (не текущий %, а ДИНАМИКА)

**Вывод для скоринга**: CoinGecko social data (watchlist, sentiment, GitHub) НЕ добавляет predictive power. Существующие факторы (Vol/MC, MC/FDV, price momentum) остаются основными. Для social signal нужен Twitter API или LunarCrush Individual ($19/мес).

*Полный отчёт: `calibration/social_report.md`*

---

## Lesson #5: Twitter followers — абсолютное число НЕ предсказывает multiplier (2026-03-11)

**Контекст**: Playwright scraping 89 из 114 winners (78% coverage). Данные объединены с multiplier и market cap из calibration study.

**Ключевые находки**:

### Абсолютный follower count — НЕ дискриминирует
- Spearman корреляция (followers vs multiplier): **-0.110** (практически ноль)
- Spearman (followers/MC ratio vs multiplier): **0.055** (тоже ноль)
- Медиана multiplier **одинакова (~2.1x)** для всех квартилей followers
- Per-cluster корреляция: все около нуля (A: -0.024, B: -0.099, C: -0.303, E: -0.009)

### Маленькие аккаунты — больший upside, но это артефакт MC
- < 10K followers: mean mult **11.0x**, max **165.5x**
- 100K+ followers: mean mult **2.7x**, max **11.0x**
- **Причина**: маленький MC → мало followers И маленький MC → больший потенциал роста
- Это НЕ каузальная связь, а confounding variable (MC)

### Медиана followers по кластерам
| Кластер | Медиана | Среднее |
|---------|---------|---------|
| B_gradual_accumulation | 89,600 | 113,626 |
| A_deep_recovery | 72,350 | 152,507 |
| D_momentum_continuation | 114,700 | 122,266 |
| E_v_reversal | 36,100 | 148,075 |
| C_breakout_sideways | 35,600 | 194,991 |

- B_gradual имеет наивысшую медиану — совпадает с находкой про Telegram (94%)
- C_breakout и E_v_reversal — низкие медианы, широкий разброс

### Что НУЖНО, но недоступно
- **Twitter follower GROWTH RATE** (7-30 дней до пампа) — рост community = потенциальный leading indicator
- **Engagement rate** (likes/retweets per follower) — качество аудитории
- **KOL mention velocity** — скорость роста упоминаний инфлюенсерами
- Все требуют платный Twitter API или LunarCrush

**Вывод для скоринга**: Абсолютное число Twitter followers = **0 баллов** в скоринге. Отражает "размер проекта" (proxy для MC), а не потенциал роста. Единственный потенциально полезный social metric — **ТЕМПЫ РОСТА** followers/mentions, но данные недоступны бесплатно. Social scoring dimension в текущей модели должен опираться на: narrative phase + catalyst proximity, НЕ на follower counts.

*Полный отчёт: `calibration/twitter_report.md`*

---

## Lesson #6: Binance деривативные метрики — basis > funding > volume (2026-03-11)

**Контекст**: Калибровочное исследование 137 winners (2x+) vs 67 losers (-50%+), все на Binance спот+фьючерсы. Собраны: spot klines, futures klines, funding rate, mark/index price за T-60 to T+5.

**Ключевые находки**:

### Futures-Spot Basis — СИЛЬНЕЙШИЙ деривативный сигнал (p=0.005)
- Winners basis 30d: **-0.078%** (фьючерсы ДЕШЕВЛЕ спота)
- Losers basis 30d: **-0.059%**
- Winners basis persistence (доля дней с премией): **6.7%** vs Losers **10%**
- **Интерпретация**: Перед пампом фьючерсный рынок ПЕССИМИСТИЧЕН → шорты давят → squeeze fuel
- **Правило**: Persistent futures discount + declining spot volume = strongest pre-pump setup

### Futures/Spot Volume Ratio — значим на T-30 (p=0.033), НЕ на T-7
- Winners F/S ratio T-30: **3.48** vs Losers **4.15**
- На T-7: 3.64 vs 3.30, p=0.97 — разница ИСЧЕЗАЕТ
- **Интерпретация**: Спотовое накопление (lower leverage) предшествует пампам. К T-7 leverage подключается.
- Самые сильные пампы (3x+) = lowest F/S ratio (3.23)

### Funding Rate — ГИПОТЕЗА ОПРОВЕРГНУТА
- Persistence: Winners 0.794 vs Losers 0.833, p=0.28
- Avg, max, annualized — все незначимые (p > 0.21)
- **Вывод**: Положительный фандинг = общий фон рынка, не токен-специфический сигнал
- **Исключение**: funding × vol_growth interaction значим (p=0.044) — высокий фандинг + снижающийся объём = тихое накопление под давлением шортов

### Market Cap — подтверждён из новой выборки (p=0.000003)
- Winners: median **$67M**, Losers: median **$150M**
- Sweet spot для 2x на Binance = small-cap ($50-100M)

### Что НЕ работает
- **Taker Buy Ratio**: 0.488 vs 0.493, difference 0.5% — не actionable
- **Абсолютные объёмы**: spot и futures volume не дискриминируют (p > 0.15)
- **F/S ratio на T-7**: разница исчезает к моменту движения

**Для скоринга**: Добавлено 3 новых метрики:
1. Basis 30d avg (вес в Derivatives dimension: +2 при < -0.08%)
2. Basis persistence (< 10% = +1)
3. F/S vol ratio T-30 (< 3.0 = +1, > 5.0 = -1, > 8.0 = gate warning)
Убраны из рассмотрения: funding rate metrics, taker buy ratio, absolute volumes.

*Полный отчёт: `calibration/binance_calibration_report.md`*
