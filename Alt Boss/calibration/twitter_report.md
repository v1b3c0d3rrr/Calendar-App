# Twitter Followers Analysis Report

**Дата**: 2026-03-11
**Источник**: Playwright scraping X/Twitter profiles
**Выборка**: 89 из 114 winners (78% coverage)

## Методология

1. Получены Twitter handles через CoinGecko API для 114 winners с `has_twitter=True`
2. Playwright headless browser скрапил профили X/Twitter, извлекая follower counts
3. 89 успешных scrape (25 parse_failed/not_found — Twitter не рендерит для headless)
4. Данные объединены с multiplier и market cap из calibration study

## Ключевые метрики

| Метрика | Значение |
|---------|----------|
| Общая медиана followers | 48,100 |
| Общее среднее followers | 150,935 |
| Диапазон | 4 — 2,600,000 |
| Spearman (followers vs multiplier) | **-0.110** |
| Spearman (followers/MC vs multiplier) | **0.055** |

## Followers по кластерам

| Кластер | N | Медиана | Среднее | Min | Max |
|---------|---|---------|---------|-----|-----|
| A_deep_recovery | 26 | 72,350 | 152,507 | 5,581 | 1,500,000 |
| B_gradual_accumulation | 14 | 89,600 | 113,626 | 741 | 456,400 |
| C_breakout_sideways | 16 | 35,600 | 194,991 | 4 | 2,600,000 |
| D_momentum_continuation | 5 | 114,700 | 122,266 | 28 | 276,700 |
| E_v_reversal | 28 | 36,100 | 148,075 | 723 | 1,200,000 |

### Наблюдения по кластерам
- **B_gradual** имеет НАИВЫСШУЮ медиану (89,600) — проекты с Telegram community (94%) также имеют сильное Twitter-присутствие
- **C_breakout** и **E_v_reversal** — НАИМЕНЬШАЯ медиана (35-36K), широчайший разброс (bittensor subnets с 549 vs CATI с 2.6M)
- **D_momentum** — малая выборка (n=5), нерелевантно статистически

## Корреляция с multiplier

### Квартильный анализ (followers → multiplier)
| Квартиль | Followers диапазон | Медиана mult | Среднее mult | Max mult |
|----------|-------------------|-------------|-------------|----------|
| Q1 (наименьшие) | 4 — 11,300 | 2.1x | 9.9x | 165.5x |
| Q2 | 13,400 — 47,200 | 2.3x | 5.1x | 49.0x |
| Q3 | 48,100 — 125,900 | 2.1x | 2.4x | 6.6x |
| Q4 (наибольшие) | 143,100 — 2,600,000 | 2.1x | 2.8x | 11.0x |

### Tier анализ
| Tier | N | Медиана mult | Среднее mult | Max mult |
|------|---|-------------|-------------|----------|
| < 10K followers | 19 | 2.1x | 11.0x | 165.5x |
| 10K-100K | 42 | 2.2x | 3.9x | 49.0x |
| 100K+ | 28 | 2.1x | 2.7x | 11.0x |

### Per-cluster Spearman
| Кластер | N | Spearman | Интерпретация |
|---------|---|----------|---------------|
| A_deep_recovery | 26 | -0.024 | Нулевая |
| B_gradual_accumulation | 14 | -0.099 | Нулевая |
| C_breakout_sideways | 16 | -0.303 | Слабо отрицательная |
| D_momentum_continuation | 5 | +0.200 | Недостаточно данных |
| E_v_reversal | 28 | -0.009 | Нулевая |

## Выводы

### 1. Twitter followers НЕ предсказывают multiplier
Корреляция -0.110 (общая) и 0.055 (followers/MC). Медиана multiplier одинакова (~2.1x) для всех квартилей followers.

### 2. МАЛЕНЬКИЕ аккаунты = больший upside (но не сигнал)
Tokens с <10K followers показывают среднее 11.0x vs 2.7x для 100K+. Но это СЛЕДСТВИЕ малой MC, а не каузальная связь. Маленький MC → маленькие followers И маленький MC → больший потенциал роста.

### 3. Абсолютный follower count отражает "размер проекта"
Высокие followers коррелируют с высокой MC. Это лаgging характеристика, не leading indicator.

### 4. НЕ использовать followers в scoring
Добавление followers в скоринг модели не улучшит предсказательную силу. Рекомендация: **0 баллов** за абсолютное число followers.

### 5. Что МОГЛО БЫ работать (но недоступно бесплатно)
- **Follower GROWTH RATE** (7-30 дней до пампа) — рост community может быть leading indicator
- **Engagement rate** (likes/retweets per follower) — качество аудитории
- **KOL mention density** — сколько инфлюенсеров обсуждают проект

## Файлы
- `twitter_handles.json` — 114 Twitter handles из CoinGecko
- `twitter_followers.json` — 89 успешных scrape + 25 ошибок
- `scrape_twitter_followers.py` — основной скрипт
