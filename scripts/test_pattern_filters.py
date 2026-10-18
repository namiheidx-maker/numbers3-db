#!/usr/bin/env python3
"""
一般的なパターン指標でストレート傾向をさらに改善できるか検証

指標：
1. 奇偶パターン（奇数の個数で分類）
2. 高低パターン（5以上/以下で分類）
3. 重複有無
"""
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect


def get_straight_only(conn, at_draw_no: int, min_count: int = 2):
    """ストレート傾向のみ"""
    results = conn.execute(
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
           SELECT nw.number
           FROM num_wins nw
           LEFT JOIN num_gaps ng ON nw.number = ng.number
           WHERE nw.win_count >= ? AND (ng.avg_interval IS NULL OR ? - nw.last_win_draw_no >= ng.avg_interval)""",
        (at_draw_no, at_draw_no, at_draw_no, min_count, at_draw_no)
    ).fetchall()
    return {r[0] for r in results}


def filter_by_recent_patterns(conn, candidates, at_draw_no: int, lookback: int = 50):
    """直近50回のパターン分布に合致する候補を優先"""

    # 直近50回のパターンを取得
    recent = conn.execute(
        "SELECT number FROM draws WHERE draw_no > ? AND draw_no <= ? ORDER BY draw_no DESC LIMIT ?",
        (at_draw_no - lookback, at_draw_no, lookback)
    ).fetchall()

    if not recent:
        return candidates

    recent_nums = [r[0] for r in recent]

    # 各パターンを抽出
    def get_pattern(num):
        digits = [int(d) for d in num]
        odd_count = sum(1 for d in digits if d % 2 == 1)
        high_count = sum(1 for d in digits if d >= 5)
        has_dup = len(set(digits)) < 3
        return (odd_count, high_count, has_dup)

    recent_patterns = [get_pattern(num) for num in recent_nums]
    pattern_dist = Counter(recent_patterns)
    most_common_pattern = pattern_dist.most_common(1)[0][0]

    # 最頻パターンに合う候補を優先
    preferred = []
    other = []

    for cand in candidates:
        if get_pattern(cand) == most_common_pattern:
            preferred.append(cand)
        else:
            other.append(cand)

    return preferred, other, most_common_pattern


def run_test(conn):
    """パターンフィルタの効果をテスト"""
    latest = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()[0]

    test_window = 50
    snapshot_interval = 50
    test_start = 5000
    test_end = latest - test_window

    print("=== パターンフィルタの有効性テスト ===\n")
    print(f"テスト期間: 第{test_start}回～第{test_end}回")
    print(f"各時点から{test_window}回先までを検証\n")

    results_straight = []
    results_pattern = []

    for draw_no in range(test_start, test_end, snapshot_interval):
        # ストレート傾向のみ
        candidates_straight = get_straight_only(conn, draw_no, 2)

        # パターンフィルタを適用
        if candidates_straight:
            preferred, other, pattern = filter_by_recent_patterns(conn, candidates_straight, draw_no)
        else:
            preferred = []
            other = []
            pattern = None

        # テスト（実際の当選）
        test_results = conn.execute(
            "SELECT number FROM draws WHERE draw_no > ? AND draw_no <= ? ORDER BY draw_no",
            (draw_no, draw_no + test_window)
        ).fetchall()

        if not test_results:
            continue

        test_numbers = [r[0] for r in test_results]
        test_count = len(test_numbers)

        # ストレート傾向のみ
        hits_straight = sum(1 for num in test_numbers if num in candidates_straight)
        results_straight.append({"hits": hits_straight, "test": test_count, "cands": len(candidates_straight)})

        # パターンフィルタ適用
        # 優先パターンから的中、その後一般パターンから的中
        hits_pattern = sum(1 for num in test_numbers if num in preferred)
        results_pattern.append({"hits": hits_pattern, "test": test_count, "cands": len(preferred)})

    # 結果集計
    if results_straight:
        total_straight = sum(r["test"] for r in results_straight)
        hits_straight = sum(r["hits"] for r in results_straight)
        rate_straight = hits_straight / total_straight * 100 if total_straight else 0

        total_pattern = sum(r["test"] for r in results_pattern)
        hits_pattern = sum(r["hits"] for r in results_pattern)
        rate_pattern = hits_pattern / total_pattern * 100 if total_pattern else 0

        print("方式                | 的中率   | 的中数 | 候補数 | 評価")
        print("---------------------|---------|--------|--------|-------")
        print(f"ストレート傾向のみ    | {rate_straight:6.2f}% | {hits_straight:6} | {sum(r['cands'] for r in results_straight)/len(results_straight):6.1f} |")
        print(f"+ パターンフィルタ    | {rate_pattern:6.2f}% | {hits_pattern:6} | {sum(r['cands'] for r in results_pattern)/len(results_pattern):6.1f} |", end="")

        if rate_pattern > rate_straight:
            improvement = (rate_pattern - rate_straight) / rate_straight * 100
            print(f" ✅ {improvement:+.1f}%")
        elif rate_pattern < rate_straight:
            decline = (rate_pattern - rate_straight) / rate_straight * 100
            print(f" ❌ {decline:+.1f}%")
        else:
            print(" ⚪ 同等")
    else:
        print("テストデータなし")


if __name__ == "__main__":
    conn = connect()
    try:
        run_test(conn)
    finally:
        conn.close()
