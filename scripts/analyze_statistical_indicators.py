#!/usr/bin/env python3
"""
ナンバーズ3 予想精度向上のための数学的指標分析

候補：
1. 当選回数の分散 - 出現のばらつきが大きい数字は予測しやすいか
2. 平均値vs中央値の乖離 - 外れ値の影響度
3. 間隔の標準偏差 - 出現パターンの規則性
4. 連続出現スコア - 最近連続して出現する数字
5. キャップイン比 - 最大間隔/最小間隔
"""
import sys
from pathlib import Path
import statistics

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect


def analyze_indicators(conn, at_draw_no: int, top_count: int = 10):
    """各指標を計算して、当選予測精度との相関を検証"""

    # ストレート候補を取得
    candidates = conn.execute(
        """WITH num_wins AS (
             SELECT number, COUNT(*) as win_count, MAX(draw_no) as last_win_draw_no
             FROM draws WHERE draw_no <= ? GROUP BY number
           ),
           num_gaps AS (
             SELECT number,
                    CASE
                      WHEN COUNT(*) <= 1 THEN NULL
                      ELSE CAST(? - (SELECT MIN(draw_no) FROM draws) AS FLOAT) / (COUNT(*) - 1)
                    END as avg_interval
             FROM draws WHERE draw_no <= ? GROUP BY number
           )
           SELECT nw.number, nw.win_count, nw.last_win_draw_no, ng.avg_interval
           FROM num_wins nw
           LEFT JOIN num_gaps ng ON nw.number = ng.number
           WHERE nw.win_count >= 2 AND (ng.avg_interval IS NULL OR ? - nw.last_win_draw_no >= ng.avg_interval)
           ORDER BY nw.win_count DESC, nw.last_win_draw_no ASC
           LIMIT ?""",
        (at_draw_no, at_draw_no, at_draw_no, at_draw_no, top_count)
    ).fetchall()

    results = []

    for number, win_count, last_draw, avg_interval in candidates:
        # 出現間隔の全データを取得
        intervals_data = conn.execute(
            """WITH draws_for_num AS (
                 SELECT draw_no FROM draws WHERE draw_no <= ? AND number = ? ORDER BY draw_no
               ),
               with_lags AS (
                 SELECT draw_no, LAG(draw_no) OVER (ORDER BY draw_no) as prev_draw
                 FROM draws_for_num
               )
               SELECT draw_no - prev_draw as interval FROM with_lags WHERE prev_draw IS NOT NULL""",
            (at_draw_no, number)
        ).fetchall()

        intervals = [row[0] for row in intervals_data]

        if len(intervals) < 2:
            continue

        # 指標の計算
        mean_interval = statistics.mean(intervals)
        median_interval = statistics.median(intervals)
        stdev_interval = statistics.stdev(intervals)
        min_interval = min(intervals)
        max_interval = max(intervals)

        # 最近の連続出現スコア（直近20回で何回出現したか）
        recent_count = conn.execute(
            "SELECT COUNT(*) FROM draws WHERE draw_no > ? AND draw_no <= ? AND number = ?",
            (at_draw_no - 20, at_draw_no, number)
        ).fetchone()[0]

        # 次の50回での的中判定（実績）
        future_hit = conn.execute(
            "SELECT COUNT(*) FROM draws WHERE draw_no > ? AND draw_no <= ? AND number = ?",
            (at_draw_no, at_draw_no + 50, number)
        ).fetchone()[0]

        results.append({
            "number": number,
            "win_count": win_count,
            "avg_interval": avg_interval,
            "mean_interval": mean_interval,
            "median_interval": median_interval,
            "stdev_interval": stdev_interval,
            "mean_median_ratio": mean_interval / median_interval if median_interval > 0 else 1.0,
            "cv_coefficient": stdev_interval / mean_interval if mean_interval > 0 else 0,  # 変動係数
            "range_interval": max_interval - min_interval,
            "cap_in_ratio": max_interval / min_interval if min_interval > 0 else 1.0,  # キャップイン比
            "recent_count": recent_count,
            "future_hit": future_hit,
        })

    return results


def compare_with_hits(results):
    """的中有無で指標を比較"""
    hits = [r for r in results if r["future_hit"] > 0]
    miss = [r for r in results if r["future_hit"] == 0]

    print("=== 的中した数字 vs 外れた数字 の指標比較 ===\n")

    if not hits or not miss:
        print("データが不足しています")
        return

    indicators = [
        ("当選回数", "win_count"),
        ("平均間隔", "mean_interval"),
        ("中央値", "median_interval"),
        ("標準偏差", "stdev_interval"),
        ("変動係数", "cv_coefficient"),
        ("キャップイン比", "cap_in_ratio"),
        ("直近20回での出現", "recent_count"),
    ]

    print("指標                | 的中平均 | 外れ平均 | 差分    | 判定")
    print("----|-----------------|---------|---------|---------|----------")

    for label, key in indicators:
        hit_avg = statistics.mean([r[key] for r in hits])
        miss_avg = statistics.mean([r[key] for r in miss])
        diff_pct = (hit_avg - miss_avg) / miss_avg * 100 if miss_avg != 0 else 0

        # 差分が大きければ、その指標は予測に有効
        mark = ""
        if abs(diff_pct) > 20:
            mark = "✅ 有効" if ((key in ["win_count", "recent_count"] and hit_avg > miss_avg) or
                            (key in ["mean_interval", "cv_coefficient"] and hit_avg < miss_avg)) else "⚠️"

        print(f"{label:15} | {hit_avg:7.2f} | {miss_avg:7.2f} | {diff_pct:+6.1f}% | {mark}")


def main():
    conn = connect()
    try:
        latest = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()[0]

        print("=== ナンバーズ3 予想精度向上のための数学的指標分析 ===\n")
        print(f"分析時点: 第{latest-50}回")
        print(f"検証期間: その後50回の当選有無\n")

        results = analyze_indicators(conn, latest - 50, top_count=20)

        if results:
            compare_with_hits(results)

            print(f"\n=== 詳細（ストレート候補 上位10個） ===\n")
            print("数字 | 当選 | 平均間 | 標偏 | 変動係 | キャップ | 直近20回 | 結果")
            print("-----|------|--------|------|--------|---------|----------|----")

            for r in results[:10]:
                result_mark = "✓" if r["future_hit"] > 0 else "✗"
                print(f"{r['number']:4} | {r['win_count']:4} | {r['mean_interval']:6.1f} | {r['stdev_interval']:4.1f} | {r['cv_coefficient']:6.2f} | {r['cap_in_ratio']:7.2f} | {r['recent_count']:8} | {result_mark}")

        else:
            print("候補が見つかりませんでした")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
