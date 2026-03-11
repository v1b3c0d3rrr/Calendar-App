"""
Строит приоритетные очереди для сбора данных:
1. Phase 2: BSC/Base токены — winners first, smallest MC first
2. Phase 5: Holder snapshots — smallest transfer_count first

Цель: быстро набрать выборку для power=0.90 (80 per group).
"""
import json
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"


def build_phase2_queue():
    """Приоритет сбора трансферов для BSC/Base/Avalanche токенов."""
    with open(DATA / "evm_tokens.json") as f:
        evm = json.load(f)["evm_tokens"]

    with open(DATA / "transfer_collection_progress.json") as f:
        progress = json.load(f)
    completed = set(progress.get("completed", []))

    uncollected = []
    for t in evm:
        if t["coin_id"] in completed:
            continue
        contracts = t.get("contracts", {})
        chain = list(contracts.keys())[0] if contracts else t.get("asset_platform_id", "?")
        contract_addr = contracts.get(chain, "")
        cat = t.get("category", "?")
        is_winner = "winner" in cat.lower()
        uncollected.append({
            "coin_id": t["coin_id"],
            "symbol": t.get("symbol", "?"),
            "category": cat,
            "is_winner": is_winner,
            "chain": chain,
            "contract": contract_addr,
            "start_mc": t.get("start_mc", 0) or 0,
            "priority": 0 if is_winner else 1,
        })

    # Sort: winners first, then by start_mc (smaller = likely fewer transfers)
    uncollected.sort(key=lambda x: (x["priority"], x["start_mc"]))

    for i, t in enumerate(uncollected):
        t["queue_position"] = i + 1

    # Stats
    winners = [t for t in uncollected if t["is_winner"]]
    losers = [t for t in uncollected if not t["is_winner"]]

    print("=" * 70)
    print("PHASE 2: BSC/Base/Avalanche Transfer Collection Queue")
    print("=" * 70)
    print(f"Total: {len(uncollected)} ({len(winners)}W + {len(losers)}L)")
    print(f"\nWinners (PRIORITY — нужно 13+ для power=0.90):")
    for t in winners:
        print(f"  #{t['queue_position']:>2} {t['coin_id']:<35} MC={t['start_mc']:>12,}  {t['chain']}")
    print(f"\nLosers (дособирать после winners):")
    for t in losers[:10]:
        print(f"  #{t['queue_position']:>2} {t['coin_id']:<35} MC={t['start_mc']:>12,}  {t['chain']}")
    print(f"  ... и ещё {len(losers)-10}")

    return uncollected


def build_phase5_queue():
    """Приоритет сбора holder snapshots — самые маленькие токены первыми."""
    import os
    transfers_dir = DATA / "transfers"

    tokens = []
    for f in sorted(os.listdir(transfers_dir)):
        if not f.endswith(".json"):
            continue
        with open(transfers_dir / f) as fp:
            d = json.load(fp)
        cat = d.get("category", "?")
        is_winner = "winner" in cat.lower()
        tokens.append({
            "coin_id": d.get("coin_id", f.replace(".json", "")),
            "symbol": d.get("symbol", "?"),
            "category": cat,
            "is_winner": is_winner,
            "chain_name": d.get("chain_name", "?"),
            "transfer_count": d.get("transfer_count", 0),
            "event_date": d.get("event_date", "?"),
        })

    # Sort by transfer_count ascending (smallest history first)
    tokens.sort(key=lambda x: x["transfer_count"])

    for i, t in enumerate(tokens):
        t["queue_position"] = i + 1

    # Cumulative stats — when do we reach target sample sizes?
    print("\n" + "=" * 70)
    print("PHASE 5: Holder Snapshot Collection Queue")
    print("=" * 70)
    print(f"Total collected tokens: {len(tokens)}")
    print(f"\nКумулятивное покрытие (по мере сбора от маленьких к большим):")
    print(f"{'#tokens':>8} {'Winners':>8} {'Losers':>8} {'Status':>25} {'Max transfers':>15}")
    print("-" * 70)

    cum_w, cum_l = 0, 0
    milestones = [20, 40, 60, 80, 100, 120, 140, 160, 180, 197]
    for i, t in enumerate(tokens):
        if t["is_winner"]:
            cum_w += 1
        else:
            cum_l += 1
        n = i + 1
        if n in milestones:
            min_group = min(cum_w, cum_l)
            if min_group >= 80:
                status = "✅ power=0.90 (d≥0.5)"
            elif min_group >= 48:
                status = "✅ power=0.90 (d≥0.68)"
            elif min_group >= 34:
                status = "⚠️  power=0.80 (d≥0.68)"
            else:
                status = "❌ недостаточно"
            print(f"{n:>8} {cum_w:>8} {cum_l:>8} {status:>25} {t['transfer_count']:>15,}")

    print(f"\nТоп-30 (самые быстрые для сбора):")
    print(f"{'#':>4} {'coin_id':<35} {'transfers':>10} {'cat':<15} {'chain':<15}")
    print("-" * 82)
    for t in tokens[:30]:
        print(f"{t['queue_position']:>4} {t['coin_id']:<35} {t['transfer_count']:>10,} "
              f"{t['category']:<15} {t['chain_name']:<15}")

    return tokens


def main():
    phase2 = build_phase2_queue()
    phase5 = build_phase5_queue()

    # Save queues
    output = {
        "phase2_bsc_base": [t["coin_id"] for t in phase2],
        "phase5_snapshots": [t["coin_id"] for t in phase5],
        "phase2_details": phase2,
        "phase5_details": phase5,
    }
    out_path = DATA / "priority_queues.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n✅ Очереди сохранены: {out_path}")

    # Summary
    print("\n" + "=" * 70)
    print("ПЛАН ДЕЙСТВИЙ")
    print("=" * 70)
    current_w = sum(1 for t in phase5 if t["is_winner"])
    current_l = sum(1 for t in phase5 if not t["is_winner"])
    need_w = max(0, 80 - current_w)
    bsc_winners = sum(1 for t in phase2 if t["is_winner"])

    print(f"Сейчас: {current_w}W + {current_l}L = {current_w+current_l} collected")
    print(f"Нужно для power=0.90 (d≥0.5): 80W + 80L")
    print(f"Bottleneck: Winners ({current_w}, нужно ещё {need_w})")
    print(f"BSC/Base winners доступно: {bsc_winners}")
    print()
    print("ШАГ 1: Прогнать labeling на ВСЕХ 197 собранных → обновить анализ")
    print(f"ШАГ 2: Собрать {min(need_w, bsc_winners)} BSC winners (самые маленькие первыми)")
    print("ШАГ 3: Запустить Phase 5 snapshots в порядке priority_queues")
    print("ШАГ 4: Параллельно дособирать BSC losers для уточнения")


if __name__ == "__main__":
    main()
