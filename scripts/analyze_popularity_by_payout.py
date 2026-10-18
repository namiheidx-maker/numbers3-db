#!/usr/bin/env python3
"""
当選金額から「人気度」を逆算する

パリミューチュエル方式：配当金 = 総売上 ÷ 当選者数
→ 配当が高い = 当選者が少ない = 選ばれにくい数字
"""
import sys
from pathlib import Path
from statistics import mean, median, stdev

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect


def analyze_payout_patterns(conn):
    """各当選数字の平均配当を計算し、人気度を分類"""

    # 全当選数字の配当を集計
    results = conn.execute(
        "SELECT number, straight_amount FROM draws ORDER BY draw_no"
    ).fetchall()

    # 数字ごとに配当を集計
    number_payouts = {}
    for number, amount in results:
        if number not in number_payouts:
            number_payouts[number] = []
        number_payouts[number].append(amount)

    # 各数字の統計
    number_stats = {}
    for number, payouts in number_payouts.items():
        number_stats[number] = {
            "count": len(payouts),
            "avg_payout": mean(payouts),
            "median_payout": median(payouts),
            "min_payout": min(payouts),
            "max_payout": max(payouts),
        }

    # 全体の平均配当
    all_payouts = [a for p in number_payouts.values() for a in p]
    overall_avg = mean(all_payouts)
    overall_median = median(all_payouts)
    overall_stdev = stdev(all_payouts)

    print("=== ナンバーズ3 当選数字の配当分析 ===\n")
    print(f"全当選数字: {len(number_stats)}個")
    print(f"全体の平均配当: ¥{overall_avg:,.0f}")
    print(f"全体の中央値: ¥{overall_median:,.0f}")
    print(f"全体の標準偏差: ¥{overall_stdev:,.0f}\n")

    # 3階級に分類
    high_threshold = overall_avg + overall_stdev * 0.5
    low_threshold = overall_avg - overall_stdev * 0.5

    unpopular = {}  # 配当が高い（不人気）
    normal = {}     # 平均的
    popular = {}    # 配当が低い（人気）

    for number, stats in number_stats.items():
        avg = stats["avg_payout"]
        if avg >= high_threshold:
            unpopular[number] = stats
        elif avg <= low_threshold:
            popular[number] = stats
        else:
            normal[number] = stats

    print(f"--- 分類結果 ---")
    print(f"不人気（配当高い）: {len(unpopular)}個 （平均 ¥{high_threshold:,.0f} 以上）")
    print(f"普通: {len(normal)}個")
    print(f"人気（配当低い）: {len(popular)}個 （平均 ¥{low_threshold:,.0f} 以下）\n")

    # 不人気数字（配当が高い）の詳細
    print("--- 不人気数字（配当が最も高い TOP20）---")
    print("数字 | 当選回数 | 平均配当 | 中央値 | 最小 | 最大")
    print("-----|---------|---------|--------|------|------")

    sorted_unpopular = sorted(unpopular.items(), key=lambda x: -x[1]["avg_payout"])
    for number, stats in sorted_unpopular[:20]:
        print(f"{number} | {stats['count']:8} | ¥{stats['avg_payout']:7,.0f} | "
              f"¥{stats['median_payout']:6,.0f} | ¥{stats['min_payout']:6,.0f} | ¥{stats['max_payout']:8,.0f}")

    # 人気数字（配当が低い）の詳細
    print(f"\n--- 人気数字（配当が最も低い TOP20）---")
    print("数字 | 当選回数 | 平均配当 | 中央値 | 最小 | 最大")
    print("-----|---------|---------|--------|------|------")

    sorted_popular = sorted(popular.items(), key=lambda x: x[1]["avg_payout"])
    for number, stats in sorted_popular[:20]:
        print(f"{number} | {stats['count']:8} | ¥{stats['avg_payout']:7,.0f} | "
              f"¥{stats['median_payout']:6,.0f} | ¥{stats['min_payout']:6,.0f} | ¥{stats['max_payout']:8,.0f}")

    # サマリー
    print(f"\n=== インサイト ===")
    print(f"配当の最大差: ¥{max(s['avg_payout'] for s in number_stats.values()):,.0f} - "
          f"¥{min(s['avg_payout'] for s in number_stats.values()):,.0f} = "
          f"¥{max(s['avg_payout'] for s in number_stats.values()) - min(s['avg_payout'] for s in number_stats.values()):,.0f}")
    print(f"\n不人気数字を選ぶと、平均配当が {max(s['avg_payout'] for s in unpopular.values()) / overall_avg:.1f}倍高い")

    return number_stats, unpopular, popular, normal


if __name__ == "__main__":
    conn = connect()
    try:
        analyze_payout_patterns(conn)
    finally:
        conn.close()
