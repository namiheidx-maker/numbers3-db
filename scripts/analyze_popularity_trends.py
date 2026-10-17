#!/usr/bin/env python3
"""
人気度別の出現傾向分析
- 不人気（高配当）、普通、人気（低配当）の当選パターンを時系列で分析
- 各カテゴリの「出現間隔」を計算（1桁間隔みたいに）
- 直近の傾向を把握
"""
import sys
from pathlib import Path
from statistics import mean, stdev

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect


def classify_number_popularity(conn):
    """各数字を「不人気」「普通」「人気」に分類"""
    from statistics import mean, stdev

    results = conn.execute(
        "SELECT number, straight_amount FROM draws ORDER BY draw_no"
    ).fetchall()

    number_payouts = {}
    for number, amount in results:
        if number not in number_payouts:
            number_payouts[number] = []
        number_payouts[number].append(amount)

    all_payouts = [a for p in number_payouts.values() for a in p]
    overall_avg = mean(all_payouts)
    overall_stdev = stdev(all_payouts)

    high_threshold = overall_avg + overall_stdev * 0.5
    low_threshold = overall_avg - overall_stdev * 0.5

    classification = {}
    for number, payouts in number_payouts.items():
        avg = mean(payouts)
        if avg >= high_threshold:
            classification[number] = "不人気"
        elif avg <= low_threshold:
            classification[number] = "人気"
        else:
            classification[number] = "普通"

    return classification


def analyze_popularity_trends(conn):
    """人気度カテゴリごとの出現パターンを分析"""

    # 当選数字を時系列で取得
    draws = conn.execute(
        "SELECT draw_no, number FROM draws ORDER BY draw_no"
    ).fetchall()

    # 人気度分類
    classification = classify_number_popularity(conn)

    # 人気度ごとにグループ化
    popularity_draws = {"不人気": [], "普通": [], "人気": []}
    for draw_no, number in draws:
        pop_level = classification[number]
        popularity_draws[pop_level].append((draw_no, number))

    latest_draw_no = draws[-1][0]

    print("=== ナンバーズ3 人気度別 出現傾向分析 ===\n")

    for pop_level in ["不人気", "普通", "人気"]:
        entries = popularity_draws[pop_level]
        count = len(entries)
        pct = count / len(draws) * 100

        # 出現間隔を計算
        if len(entries) >= 2:
            draw_nos = [e[0] for e in entries]
            intervals = [draw_nos[i+1] - draw_nos[i] for i in range(len(draw_nos)-1)]
            avg_interval = mean(intervals)
            min_interval = min(intervals)
            max_interval = max(intervals)
        else:
            avg_interval = min_interval = max_interval = None

        # 直近の傾向（最後から20回）
        recent_entries = [e for e in entries if e[0] > latest_draw_no - 20]
        recent_count = len(recent_entries)

        # 最後の出現から何回経過したか
        if entries:
            last_draw_no = entries[-1][0]
            draws_since_last = latest_draw_no - last_draw_no
        else:
            draws_since_last = None

        print(f"--- {pop_level}（高配当）数字 ---")
        print(f"全期間出現: {count}回（全体比 {pct:.1f}%）")
        if avg_interval:
            print(f"出現間隔: 平均 {avg_interval:.1f}回（最小 {min_interval}回、最大 {max_interval}回）")
        print(f"直近20回での出現: {recent_count}回")
        if draws_since_last is not None:
            print(f"最後の出現: 第{last_draw_no}回（{draws_since_last}回経過）")
        print()

    # 直近50回での分布
    print("--- 直近50回での内訳 ---")
    recent_draws = [d for d in draws if d[0] > latest_draw_no - 50]
    recent_classification = {}
    for draw_no, number in recent_draws:
        pop_level = classification[number]
        if pop_level not in recent_classification:
            recent_classification[pop_level] = 0
        recent_classification[pop_level] += 1

    for pop_level in ["不人気", "普通", "人気"]:
        count = recent_classification.get(pop_level, 0)
        pct = count / len(recent_draws) * 100
        print(f"{pop_level}: {count}回（{pct:.1f}%）")

    # 直近100回での分布
    print("\n--- 直近100回での内訳 ---")
    recent_draws_100 = [d for d in draws if d[0] > latest_draw_no - 100]
    recent_classification_100 = {}
    for draw_no, number in recent_draws_100:
        pop_level = classification[number]
        if pop_level not in recent_classification_100:
            recent_classification_100[pop_level] = 0
        recent_classification_100[pop_level] += 1

    for pop_level in ["不人気", "普通", "人気"]:
        count = recent_classification_100.get(pop_level, 0)
        pct = count / len(recent_draws_100) * 100
        print(f"{pop_level}: {count}回（{pct:.1f}%）")

    # 推奨
    print("\n=== インサイト ===")
    recent_unpopular = recent_classification_100.get("不人気", 0) / len(recent_draws_100) * 100
    overall_unpopular = sum(1 for _, n in draws if classification[n] == "不人気") / len(draws) * 100

    if recent_unpopular > overall_unpopular:
        diff = recent_unpopular - overall_unpopular
        print(f"✓ 直近100回は「不人気数字」が出やすい傾向（{diff:+.1f}pt）")
        print("  → 高額狙いモードが有利な時期の可能性")
    else:
        diff = recent_unpopular - overall_unpopular
        print(f"✗ 直近100回は「人気数字」が出やすい傾向（{diff:+.1f}pt）")
        print("  → 通常モードの方が期待値が高い可能性")


if __name__ == "__main__":
    conn = connect()
    try:
        analyze_popularity_trends(conn)
    finally:
        conn.close()
