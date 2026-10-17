#!/usr/bin/env python3
"""
人気度データベーステーブルを作成・更新
- popularity_stats テーブル: 人気、普通、不人気の全期間 + 直近30/50/100回の割合
"""
import sys
from pathlib import Path
from statistics import mean, stdev

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect


def create_popularity_table(conn):
    """popularity_stats テーブルを作成"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS popularity_stats (
            metric_name TEXT NOT NULL,
            category TEXT NOT NULL,  -- '人気', '普通', '不人気'
            percentage REAL NOT NULL,
            count INTEGER NOT NULL,
            total INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (metric_name, category)
        )
    """)
    conn.commit()


def get_popularity_classification(conn):
    """配当ベースの人気度分類を取得"""
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


def calculate_popularity_stats(conn):
    """人気度統計を計算"""
    # 当選数字を時系列で取得
    draws = conn.execute(
        "SELECT draw_no, number FROM draws ORDER BY draw_no"
    ).fetchall()

    if not draws:
        return None

    # 人気度分類を取得
    classification = get_popularity_classification(conn)

    latest_draw_no = draws[-1][0]
    total_count = len(draws)

    # 各期間のデータを抽出
    periods = {
        "全期間": (0, total_count),
        "直近30回": (max(0, total_count - 30), total_count),
        "直近50回": (max(0, total_count - 50), total_count),
        "直近100回": (max(0, total_count - 100), total_count),
    }

    stats = {}
    for period_name, (start_idx, end_idx) in periods.items():
        period_draws = draws[start_idx:end_idx]
        period_total = len(period_draws)

        counts = {"人気": 0, "普通": 0, "不人気": 0}
        for _, number in period_draws:
            pop_level = classification.get(number, "普通")
            counts[pop_level] += 1

        stats[period_name] = {
            "人気": {"count": counts["人気"], "total": period_total},
            "普通": {"count": counts["普通"], "total": period_total},
            "不人気": {"count": counts["不人気"], "total": period_total},
        }

    return stats


def update_popularity_stats_table(conn):
    """popularity_stats テーブルを更新"""
    create_popularity_table(conn)

    stats = calculate_popularity_stats(conn)
    if not stats:
        print("データが不足しています")
        return

    # 既存データを削除
    conn.execute("DELETE FROM popularity_stats")

    # 新しいデータを挿入
    for period_name, categories in stats.items():
        for category, data in categories.items():
            count = data["count"]
            total = data["total"]
            percentage = (count / total * 100) if total > 0 else 0

            conn.execute(
                """INSERT INTO popularity_stats
                   (metric_name, category, percentage, count, total)
                   VALUES (?, ?, ?, ?, ?)""",
                (period_name, category, percentage, count, total)
            )

    conn.commit()

    # 結果を表示
    print("=== 人気度データベース更新完了 ===\n")
    for period_name in ["全期間", "直近30回", "直近50回", "直近100回"]:
        print(f"【{period_name}】")
        rows = conn.execute(
            "SELECT category, percentage, count, total FROM popularity_stats WHERE metric_name = ? ORDER BY category",
            (period_name,)
        ).fetchall()
        for category, percentage, count, total in rows:
            print(f"  {category:4}: {percentage:5.1f}% ({count}/{total})")
        print()


if __name__ == "__main__":
    conn = connect()
    try:
        update_popularity_stats_table(conn)
    finally:
        conn.close()
