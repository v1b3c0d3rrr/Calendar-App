"""
Power Analysis: минимальная выборка для подтверждения onchain сигналов.

Вопрос: сколько токенов (winners + losers) нужно, чтобы с power=0.90
подтвердить статистическую значимость (alpha=0.05) для наших фичей?

Используем: Mann-Whitney U test (непараметрический).
"""

import json
import math
from pathlib import Path


def rank_biserial_to_cohens_d(r: float) -> float:
    """Конвертация rank-biserial correlation → Cohen's d."""
    return 2 * r / math.sqrt(1 - r**2)


def required_n_per_group(
    effect_d: float,
    power: float = 0.90,
    alpha: float = 0.05,
    two_sided: bool = True,
    test: str = "mann_whitney",
) -> int:
    """
    Минимальный размер каждой группы (W и L) для заданного power.

    Формула для t-test:
        n = (z_alpha + z_beta)^2 * 2 / d^2

    Для Mann-Whitney: делим на ARE ≈ 0.955 (asymptotic relative efficiency).
    При ненормальных распределениях ARE может быть ВЫШЕ (до 1.0+),
    так что это консервативная оценка.
    """
    from scipy.stats import norm

    z_alpha = norm.ppf(1 - alpha / (2 if two_sided else 1))
    z_beta = norm.ppf(power)

    # Базовый расчёт для t-test
    n_ttest = ((z_alpha + z_beta) ** 2 * 2) / (effect_d ** 2)

    if test == "mann_whitney":
        # Mann-Whitney менее эффективен на ~5% для нормальных данных
        # Для тяжёлых хвостов (наш случай — крипто) ARE > 1, но берём консервативно
        ARE = 0.955
        n = n_ttest / ARE
    else:
        n = n_ttest

    return math.ceil(n)


def main():
    # Загружаем реальные effect sizes из нашего анализа
    results_path = Path(__file__).parent.parent / "data" / "labeled" / "signal_analysis.json"

    with open(results_path) as f:
        results = json.load(f)

    features = results["feature_analysis"]

    print("=" * 80)
    print("POWER ANALYSIS: Минимальная выборка для onchain сигналов")
    print("=" * 80)
    total_w = results["dataset"]["categories"]["winner"]
    total_l = results["dataset"]["categories"]["loser"]
    total_all = results["dataset"]["total"]
    train_size = results["dataset"]["train"]

    print(f"\nПараметры: power=0.90, alpha=0.05, two-sided Mann-Whitney U test")
    print(f"Текущая выборка: {total_w}W + {total_l}L = {total_all} total ({train_size} train)")
    print()

    print(f"{'Feature':<30} {'Effect(r)':>10} {'Cohen d':>10} "
          f"{'n/group':>10} {'Total':>10} {'p-value':>10} {'Status':>15}")
    print("-" * 95)

    targets = []
    for feat in features:
        name = feat["feature"]
        r = abs(feat["effect_size"])
        p = feat["p_value"]

        if r < 0.01:
            # Тривиальный эффект — не стоит собирать
            continue

        d = rank_biserial_to_cohens_d(r)
        n = required_n_per_group(d)
        total = n * 2

        # Текущий статус
        current_w = total_w
        current_l = total_l
        current_min = min(current_w, current_l)

        if current_min >= n:
            status = "✅ ДОСТАТОЧНО"
        elif p < 0.05:
            status = "✅ УЖЕ p<0.05"
        elif p < 0.10:
            status = "⚠️  БЛИЗКО"
        else:
            status = "❌ НУЖНО БОЛЬШЕ"

        print(f"{name:<30} {r:>10.3f} {d:>10.3f} "
              f"{n:>10} {total:>10} {p:>10.4f} {status:>15}")

        targets.append({
            "feature": name,
            "effect_r": r,
            "cohen_d": d,
            "n_per_group": n,
            "total_needed": total,
            "p_value": p,
            "currently_significant": p < 0.05,
        })

    # Сводка
    print("\n" + "=" * 80)
    print("СВОДКА")
    print("=" * 80)

    # Группируем по приоритету
    strong = [t for t in targets if t["cohen_d"] >= 0.5]
    medium = [t for t in targets if 0.3 <= t["cohen_d"] < 0.5]
    weak = [t for t in targets if t["cohen_d"] < 0.3]

    if strong:
        max_n_strong = max(t["n_per_group"] for t in strong)
        print(f"\n🔴 Сильные эффекты (d ≥ 0.5): {len(strong)} фичей")
        print(f"   Нужно: {max_n_strong} на группу = {max_n_strong * 2} токенов total")
        for t in strong:
            print(f"   - {t['feature']}: d={t['cohen_d']:.3f}, need {t['n_per_group']}/group")

    if medium:
        max_n_medium = max(t["n_per_group"] for t in medium)
        print(f"\n🟡 Средние эффекты (0.3 ≤ d < 0.5): {len(medium)} фичей")
        print(f"   Нужно: {max_n_medium} на группу = {max_n_medium * 2} токенов total")
        for t in medium:
            print(f"   - {t['feature']}: d={t['cohen_d']:.3f}, need {t['n_per_group']}/group")

    if weak:
        max_n_weak = max(t["n_per_group"] for t in weak)
        print(f"\n⚪ Слабые эффекты (d < 0.3): {len(weak)} фичей")
        print(f"   Нужно: {max_n_weak} на группу = {max_n_weak * 2} токенов total")
        print(f"   (вероятно шум — не стоит собирать специально)")

    # Рекомендация
    print("\n" + "=" * 80)
    print("РЕКОМЕНДАЦИЯ")
    print("=" * 80)

    # Для подтверждения сильных + средних эффектов
    actionable = strong + medium
    if actionable:
        target_n = max(t["n_per_group"] for t in actionable)
        # Наша пропорция W:L ≈ 60:40, так что losers — bottleneck
        # Нужно target_n losers → при ratio 60:40 это target_n * 2.5 total
        ratio_w = 0.6
        ratio_l = 0.4
        total_for_losers = math.ceil(target_n / ratio_l)
        total_for_winners = math.ceil(target_n / ratio_w)
        total_needed = max(total_for_losers, total_for_winners)  # bottleneck is losers

        current_total = total_all
        additional = max(0, total_needed - current_total)

        print(f"\nДля подтверждения {len(actionable)} actionable фичей (d ≥ 0.3):")
        print(f"  Нужно: {target_n} на группу (min)")
        print(f"  При ratio W:L = 60:40 → bottleneck = losers")
        print(f"  Total нужно: ~{total_needed} токенов")
        print(f"  Сейчас есть: {current_total}")
        print(f"  Нужно дособрать: ~{additional} токенов")
        print()
        print(f"  → Собрать ещё ~{additional} токенов = ДОСТАТОЧНО для первичного")
        print(f"     подтверждения с power=0.90")
        print()

        # Уровни достаточности
        print("УРОВНИ ДОСТАТОЧНОСТИ:")
        for power_level in [0.80, 0.85, 0.90, 0.95]:
            from scipy.stats import norm
            z_a = norm.ppf(0.975)
            z_b = norm.ppf(power_level)
            min_d = min(t["cohen_d"] for t in actionable)
            n_needed = math.ceil(((z_a + z_b) ** 2 * 2) / (min_d ** 2) / 0.955)
            total_n = math.ceil(n_needed / ratio_l)
            extra = max(0, total_n - current_total)
            print(f"  Power {power_level:.0%}: {n_needed}/group → ~{total_n} total → +{extra} дополнительно")

    # Сохраняем результат
    output_path = Path(__file__).parent.parent / "data" / "power_analysis.json"
    with open(output_path, "w") as f:
        json.dump({
            "parameters": {"power": 0.90, "alpha": 0.05, "test": "mann_whitney_u"},
            "current_sample": {"total": total_all, "winners": total_w, "losers": total_l},
            "features": targets,
        }, f, indent=2)
    print(f"\nРезультаты сохранены: {output_path}")


if __name__ == "__main__":
    main()
