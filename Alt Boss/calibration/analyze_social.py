"""
Анализ social metrics по кластерам pump-типов.

Данные: CoinGecko community_data (watchlist_portfolio_users, sentiment,
github stars/forks/commits, has_twitter, has_telegram).

Цель: выявить, различаются ли social/community метрики между кластерами,
и есть ли в них предиктивная сила.

Data provided by CoinGecko (https://www.coingecko.com/en/api/)
"""

import json
import statistics
from pathlib import Path
from collections import defaultdict

OUTPUT_DIR = Path(__file__).parent


def safe_median(values):
    values = [v for v in values if v is not None and v > 0]
    if not values:
        return None
    return statistics.median(values)


def safe_mean(values):
    values = [v for v in values if v is not None and v > 0]
    if not values:
        return None
    return statistics.mean(values)


def percentile(values, p):
    values = sorted([v for v in values if v is not None and v > 0])
    if not values:
        return None
    idx = int(len(values) * p / 100)
    idx = min(idx, len(values) - 1)
    return values[idx]


def main():
    social = json.load(open(OUTPUT_DIR / "social_progress.json"))
    cluster_metrics = json.load(open(OUTPUT_DIR / "cluster_metrics_progress.json"))

    # Merge social + cluster data
    by_cluster = defaultdict(list)
    all_tokens = []

    for cid, s in social.items():
        cluster = s["cluster"]
        cg = s.get("coingecko") or {}
        cm = cluster_metrics.get(cid, {})
        multiplier = cm.get("multiplier") or cm.get("features", {}).get("multiplier", 1)

        entry = {
            "symbol": s["symbol"],
            "cluster": cluster,
            "multiplier": multiplier,
            "watchlist_users": cg.get("watchlist_portfolio_users"),
            "sentiment_up": cg.get("sentiment_votes_up_pct"),
            "sentiment_down": cg.get("sentiment_votes_down_pct"),
            "public_interest": cg.get("public_interest_score"),
            "github_stars": cg.get("github_stars"),
            "github_forks": cg.get("github_forks"),
            "github_subscribers": cg.get("github_subscribers"),
            "github_issues": cg.get("github_total_issues"),
            "github_closed_issues": cg.get("github_closed_issues"),
            "github_prs_merged": cg.get("github_pull_requests_merged"),
            "github_pr_contributors": cg.get("github_pull_request_contributors"),
            "commit_count_4w": cg.get("commit_count_4_weeks"),
            "code_additions_4w": cg.get("code_additions_4w"),
            "code_deletions_4w": cg.get("code_deletions_4w"),
            "has_twitter": cg.get("has_twitter"),
            "has_telegram": cg.get("has_telegram"),
            "has_website": cg.get("has_website"),
            "reddit_subscribers": cg.get("reddit_subscribers"),
            "reddit_posts_48h": cg.get("reddit_avg_posts_48h"),
            "reddit_comments_48h": cg.get("reddit_avg_comments_48h"),
            "telegram_users": cg.get("telegram_channel_user_count"),
            "twitter_followers": cg.get("twitter_followers"),
        }

        by_cluster[cluster].append(entry)
        all_tokens.append(entry)

    # === ANALYSIS ===
    print("=" * 70)
    print("SOCIAL METRICS BY CLUSTER — ANALYSIS REPORT")
    print("=" * 70)

    cluster_order = [
        "A_deep_recovery",
        "B_gradual_accumulation",
        "C_breakout_sideways",
        "D_momentum_continuation",
        "E_v_reversal",
    ]

    # 1. Watchlist Portfolio Users (proxy for "attention/popularity")
    print("\n" + "=" * 70)
    print("1. WATCHLIST PORTFOLIO USERS (CoinGecko)")
    print("   Proxy: сколько людей отслеживают токен на CoinGecko")
    print("=" * 70)

    for cl in cluster_order:
        group = by_cluster.get(cl, [])
        vals = [e["watchlist_users"] for e in group]
        med = safe_median(vals)
        avg = safe_mean(vals)
        p25 = percentile(vals, 25)
        p75 = percentile(vals, 75)
        n = len([v for v in vals if v and v > 0])

        # Correlation with multiplier
        pairs = [(e["watchlist_users"], e["multiplier"]) for e in group
                 if e["watchlist_users"] and e["watchlist_users"] > 0 and e["multiplier"]]

        print(f"\n  {cl} (n={len(group)}, with data={n}):")
        print(f"    Median: {med:,.0f}" if med else "    Median: N/A")
        print(f"    Mean:   {avg:,.0f}" if avg else "    Mean: N/A")
        print(f"    P25:    {p25:,.0f}" if p25 else "    P25: N/A")
        print(f"    P75:    {p75:,.0f}" if p75 else "    P75: N/A")

        if pairs:
            # Simple correlation: high watchlist vs multiplier
            sorted_pairs = sorted(pairs, key=lambda x: x[0])
            bottom_half = sorted_pairs[:len(sorted_pairs)//2]
            top_half = sorted_pairs[len(sorted_pairs)//2:]
            bot_mult = safe_median([p[1] for p in bottom_half])
            top_mult = safe_median([p[1] for p in top_half])
            if bot_mult and top_mult:
                print(f"    Low WL median mult: {bot_mult:.1f}x | High WL median mult: {top_mult:.1f}x")

    # 2. Sentiment
    print("\n" + "=" * 70)
    print("2. SENTIMENT VOTES (CoinGecko)")
    print("   sentiment_votes_up_percentage")
    print("=" * 70)

    for cl in cluster_order:
        group = by_cluster.get(cl, [])
        vals = [e["sentiment_up"] for e in group if e["sentiment_up"] is not None]
        med = safe_median(vals) if vals else None
        n = len(vals)

        print(f"\n  {cl} (with data={n}/{len(group)}):")
        if med:
            print(f"    Median sentiment_up: {med:.1f}%")
            down_vals = [e["sentiment_down"] for e in group if e["sentiment_down"] is not None]
            down_med = safe_median(down_vals) if down_vals else None
            if down_med:
                print(f"    Median sentiment_down: {down_med:.1f}%")
        else:
            print("    No sentiment data")

    # 3. GitHub activity
    print("\n" + "=" * 70)
    print("3. GITHUB ACTIVITY")
    print("=" * 70)

    for cl in cluster_order:
        group = by_cluster.get(cl, [])
        has_gh = sum(1 for e in group if e["github_stars"] and e["github_stars"] > 0)
        commits = [e["commit_count_4w"] for e in group]
        stars = [e["github_stars"] for e in group]
        prs = [e["github_prs_merged"] for e in group]

        commit_med = safe_median(commits)
        stars_med = safe_median(stars)
        prs_med = safe_median(prs)

        print(f"\n  {cl} (n={len(group)}):")
        print(f"    Has GitHub: {has_gh}/{len(group)} ({100*has_gh//len(group) if group else 0}%)")
        print(f"    Commits (4w) median: {commit_med}" if commit_med else "    Commits: N/A or 0")
        print(f"    Stars median: {stars_med}" if stars_med else "    Stars: N/A")
        print(f"    PRs merged median: {prs_med}" if prs_med else "    PRs: N/A")

    # 4. Social presence flags
    print("\n" + "=" * 70)
    print("4. SOCIAL PRESENCE FLAGS")
    print("=" * 70)

    for cl in cluster_order:
        group = by_cluster.get(cl, [])
        has_tw = sum(1 for e in group if e.get("has_twitter"))
        has_tg = sum(1 for e in group if e.get("has_telegram"))
        has_web = sum(1 for e in group if e.get("has_website"))
        has_reddit = sum(1 for e in group if e.get("reddit_subscribers") and e["reddit_subscribers"] > 0)

        print(f"\n  {cl} (n={len(group)}):")
        print(f"    Twitter: {has_tw}/{len(group)} ({100*has_tw//len(group) if group else 0}%)")
        print(f"    Telegram: {has_tg}/{len(group)} ({100*has_tg//len(group) if group else 0}%)")
        print(f"    Website: {has_web}/{len(group)} ({100*has_web//len(group) if group else 0}%)")
        print(f"    Reddit: {has_reddit}/{len(group)} ({100*has_reddit//len(group) if group else 0}%)")

    # 5. Watchlist vs Multiplier correlation (across all)
    print("\n" + "=" * 70)
    print("5. WATCHLIST SIZE vs MULTIPLIER (all tokens)")
    print("=" * 70)

    all_pairs = [(e["watchlist_users"], e["multiplier"], e["symbol"], e["cluster"])
                 for e in all_tokens
                 if e["watchlist_users"] and e["watchlist_users"] > 0 and e["multiplier"]]

    all_pairs.sort(key=lambda x: x[0])

    # Split into quartiles
    n = len(all_pairs)
    q_size = n // 4

    for qi, label in enumerate(["Q1 (smallest)", "Q2", "Q3", "Q4 (largest)"]):
        start = qi * q_size
        end = start + q_size if qi < 3 else n
        q = all_pairs[start:end]
        wl_range = f"{q[0][0]:,.0f} - {q[-1][0]:,.0f}"
        mult_med = safe_median([p[1] for p in q])
        print(f"\n  {label}: WL {wl_range}")
        print(f"    Median multiplier: {mult_med:.1f}x" if mult_med else "    Median mult: N/A")
        print(f"    Tokens: {', '.join(p[2] for p in q[:5])}{'...' if len(q) > 5 else ''}")

    # 6. Top and bottom watchlist tokens
    print("\n" + "=" * 70)
    print("6. EXTREME WATCHLIST VALUES")
    print("=" * 70)

    all_pairs.sort(key=lambda x: -x[0])
    print("\n  Top 10 most watched:")
    for wl, mult, sym, cl in all_pairs[:10]:
        print(f"    {sym:12s} WL: {wl:>8,.0f}  mult: {mult:>6.1f}x  ({cl})")

    print("\n  Bottom 10 least watched:")
    for wl, mult, sym, cl in all_pairs[-10:]:
        print(f"    {sym:12s} WL: {wl:>8,.0f}  mult: {mult:>6.1f}x  ({cl})")

    # 7. Sentiment vs Multiplier
    print("\n" + "=" * 70)
    print("7. SENTIMENT vs MULTIPLIER")
    print("=" * 70)

    sent_pairs = [(e["sentiment_up"], e["multiplier"], e["symbol"], e["cluster"])
                  for e in all_tokens
                  if e["sentiment_up"] is not None and e["multiplier"]]

    if sent_pairs:
        sent_pairs.sort(key=lambda x: x[0])
        mid = len(sent_pairs) // 2
        low_sent = sent_pairs[:mid]
        high_sent = sent_pairs[mid:]

        low_mult = safe_median([p[1] for p in low_sent])
        high_mult = safe_median([p[1] for p in high_sent])

        print(f"\n  Low sentiment (<{sent_pairs[mid][0]:.0f}%): median mult = {low_mult:.1f}x (n={len(low_sent)})")
        print(f"  High sentiment (>={sent_pairs[mid][0]:.0f}%): median mult = {high_mult:.1f}x (n={len(high_sent)})")

        # By cluster
        for cl in cluster_order:
            cl_sent = [p for p in sent_pairs if p[3] == cl]
            if len(cl_sent) >= 4:
                mid2 = len(cl_sent) // 2
                lo = safe_median([p[1] for p in cl_sent[:mid2]])
                hi = safe_median([p[1] for p in cl_sent[mid2:]])
                if lo and hi:
                    print(f"    {cl}: low_sent mult={lo:.1f}x vs high_sent mult={hi:.1f}x")

    # 8. Summary table
    print("\n" + "=" * 70)
    print("8. SUMMARY TABLE")
    print("=" * 70)

    print(f"\n  {'Cluster':<30s} {'WL med':>8s} {'Sent%':>6s} {'GH%':>5s} {'TW%':>5s} {'TG%':>5s}")
    print("  " + "-" * 60)

    for cl in cluster_order:
        group = by_cluster.get(cl, [])
        wl_med = safe_median([e["watchlist_users"] for e in group])
        sent_med = safe_median([e["sentiment_up"] for e in group if e["sentiment_up"] is not None])
        gh_pct = 100 * sum(1 for e in group if e["github_stars"] and e["github_stars"] > 0) // len(group) if group else 0
        tw_pct = 100 * sum(1 for e in group if e.get("has_twitter")) // len(group) if group else 0
        tg_pct = 100 * sum(1 for e in group if e.get("has_telegram")) // len(group) if group else 0

        wl_s = f"{wl_med:,.0f}" if wl_med else "N/A"
        sent_s = f"{sent_med:.0f}" if sent_med else "N/A"
        print(f"  {cl:<30s} {wl_s:>8s} {sent_s:>6s} {gh_pct:>4d}% {tw_pct:>4d}% {tg_pct:>4d}%")

    # 9. Key findings
    print("\n" + "=" * 70)
    print("9. KEY FINDINGS")
    print("=" * 70)

    # Compare clusters by watchlist
    cluster_wl = {}
    for cl in cluster_order:
        group = by_cluster.get(cl, [])
        med = safe_median([e["watchlist_users"] for e in group])
        cluster_wl[cl] = med

    sorted_wl = sorted(cluster_wl.items(), key=lambda x: x[1] or 0, reverse=True)
    print(f"\n  Watchlist ranking (most → least watched):")
    for cl, wl in sorted_wl:
        print(f"    {cl}: {wl:,.0f}" if wl else f"    {cl}: N/A")

    # Discriminating power
    max_wl = max(v for v in cluster_wl.values() if v)
    min_wl = min(v for v in cluster_wl.values() if v)
    if min_wl:
        ratio = max_wl / min_wl
        print(f"\n  Max/Min watchlist ratio across clusters: {ratio:.1f}x")
        if ratio > 3:
            print("  → DISCRIMINATING: watchlist size varies significantly across clusters")
        else:
            print("  → WEAK discriminator: watchlist doesn't vary much across clusters")

    # Save results
    results = {
        "summary": {},
        "by_cluster": {},
    }

    for cl in cluster_order:
        group = by_cluster.get(cl, [])
        results["by_cluster"][cl] = {
            "count": len(group),
            "watchlist_median": safe_median([e["watchlist_users"] for e in group]),
            "watchlist_mean": safe_mean([e["watchlist_users"] for e in group]),
            "watchlist_p25": percentile([e["watchlist_users"] for e in group], 25),
            "watchlist_p75": percentile([e["watchlist_users"] for e in group], 75),
            "sentiment_up_median": safe_median([e["sentiment_up"] for e in group if e["sentiment_up"] is not None]),
            "github_pct": 100 * sum(1 for e in group if e["github_stars"] and e["github_stars"] > 0) / len(group) if group else 0,
            "twitter_pct": 100 * sum(1 for e in group if e.get("has_twitter")) / len(group) if group else 0,
            "telegram_pct": 100 * sum(1 for e in group if e.get("has_telegram")) / len(group) if group else 0,
            "commits_4w_median": safe_median([e["commit_count_4w"] for e in group]),
        }

    with open(OUTPUT_DIR / "social_analysis.json", "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved: {OUTPUT_DIR / 'social_analysis.json'}")

    print(f"\n{'='*70}")
    print("Data provided by CoinGecko (https://www.coingecko.com/en/api/)")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
