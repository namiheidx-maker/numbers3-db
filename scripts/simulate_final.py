#!/usr/bin/env python3
"""
ナンバーズ3 ピックアップロジック 最終シミュレーション
可能な限りの期間でテスト、改善案の実装
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect


def get_candidates_standard(conn, at_draw_no: int, min_count: int = 2, top: int = 10):
    """標準ロジック"""
    straight_rows = conn.execute(
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
           WHERE nw.win_count >= ?
           ORDER BY nw.win_count DESC, nw.last_win_draw_no ASC""",
        (at_draw_no, at_draw_no, at_draw_no, min_count)
    ).fetchall()

    digit_data = conn.execute(
        """WITH digit_table AS (
             SELECT '0' as d FROM draws WHERE draw_no <= ? AND (number LIKE '0%' OR number LIKE '%0%' OR number LIKE '%0')
             UNION ALL SELECT '1' FROM draws WHERE draw_no <= ? AND (number LIKE '1%' OR number LIKE '%1%' OR number LIKE '%1')
             UNION ALL SELECT '2' FROM draws WHERE draw_no <= ? AND (number LIKE '2%' OR number LIKE '%2%' OR number LIKE '%2')
             UNION ALL SELECT '3' FROM draws WHERE draw_no <= ? AND (number LIKE '3%' OR number LIKE '%3%' OR number LIKE '%3')
             UNION ALL SELECT '4' FROM draws WHERE draw_no <= ? AND (number LIKE '4%' OR number LIKE '%4%' OR number LIKE '%4')
             UNION ALL SELECT '5' FROM draws WHERE draw_no <= ? AND (number LIKE '5%' OR number LIKE '%5%' OR number LIKE '%5')
             UNION ALL SELECT '6' FROM draws WHERE draw_no <= ? AND (number LIKE '6%' OR number LIKE '%6%' OR number LIKE '%6')
             UNION ALL SELECT '7' FROM draws WHERE draw_no <= ? AND (number LIKE '7%' OR number LIKE '%7%' OR number LIKE '%7')
             UNION ALL SELECT '8' FROM draws WHERE draw_no <= ? AND (number LIKE '8%' OR number LIKE '%8%' OR number LIKE '%8')
             UNION ALL SELECT '9' FROM draws WHERE draw_no <= ? AND (number LIKE '9%' OR number LIKE '%9%' OR number LIKE '%9')
           )
           SELECT d FROM digit_table GROUP BY d HAVING COUNT(*) >= ?""",
        tuple([at_draw_no] * 10 + [min_count])
    ).fetchall()

    digit_candidates = {row[0] for row in digit_data}

    matched = []
    for number, win_count, last_win_draw_no, avg_interval in straight_rows:
        if avg_interval is None:
            passes = True
        else:
            draws_elapsed = at_draw_no - last_win_draw_no
            passes = draws_elapsed >= avg_interval

        if passes and all(ch in digit_candidates for ch in str(number)):
            matched.append({"number": str(number), "win_count": win_count, "last_draw": last_win_draw_no})

    return matched[:top]


def get_candidates_with_short_term_trend(conn, at_draw_no: int, min_count: int = 2, top: int = 10, short_window: int = 365):
    """改善1: 短期（直近1年）と長期トレンドを比較"""
    matched_std = get_candidates_standard(conn, at_draw_no, min_count, top)

    # 短期での当選回数を取得
    filtered = []
    for c in matched_std:
        short_term_count = conn.execute(
            "SELECT COUNT(*) FROM draws WHERE draw_no > ? AND draw_no <= ? AND number = ?",
            (at_draw_no - short_window, at_draw_no, c["number"])
        ).fetchone()[0]

        # 短期で当選している（最近活発）な数字を優先
        if short_term_count > 0:
            filtered.append((c, short_term_count))

    # 短期当選数が多い順にソート、なければ元の順序を保持
    if filtered:
        filtered.sort(key=lambda x: -x[1])
        return [c for c, _ in filtered]
    else:
        return matched_std


def get_candidates_clustering_enhanced(conn, at_draw_no: int, min_count: int = 2, top: int = 10):
    """改善2: クラスタリング検出（最近20回で複数回出現）"""
    matched_std = get_candidates_standard(conn, at_draw_no, min_count, top)

    # 最近20回でのクラスタリング検出
    cluster_threshold = 2
    filtered = []

    for c in matched_std:
        recent_count = conn.execute(
            "SELECT COUNT(*) FROM draws WHERE draw_no > ? AND draw_no <= ? AND number = ?",
            (at_draw_no - 20, at_draw_no, c["number"])
        ).fetchone()[0]

        # クラスタリング傾向がある数字を優先
        if recent_count >= cluster_threshold:
            filtered.append((c, recent_count))
        else:
            filtered.append((c, 0))

    # クラスタリングスコアが高い順
    filtered.sort(key=lambda x: (-x[1], -x[0]["win_count"]))
    return [c for c, _ in filtered]


def get_candidates_short_long_intervals(conn, at_draw_no: int, min_count: int = 2, top: int = 10):
    """改善3: 短期平均間隔 > 長期平均間隔の数字を優先（トレンド転換を捉える）"""
    matched_std = get_candidates_standard(conn, at_draw_no, min_count, top)

    short_window = 365
    scored = []

    for c in matched_std:
        # 短期（直近1年）での出現間隔
        short_results = conn.execute(
            "SELECT draw_no FROM draws WHERE draw_no > ? AND draw_no <= ? AND number = ? ORDER BY draw_no",
            (at_draw_no - short_window, at_draw_no, c["number"])
        ).fetchall()

        # 長期（全体）での出現間隔
        long_results = conn.execute(
            "SELECT draw_no FROM draws WHERE draw_no <= ? AND number = ? ORDER BY draw_no",
            (at_draw_no, c["number"])
        ).fetchall()

        short_avg = _calc_avg_interval(short_results, at_draw_no)
        long_avg = _calc_avg_interval(long_results, at_draw_no)

        # 短期が長期より狭い（最近出現しやすい）スコア
        if long_avg and short_avg:
            ratio = short_avg / long_avg if short_avg > 0 else 1.0
        else:
            ratio = 1.0

        scored.append((c, ratio))

    # 短期が有利な比率でソート
    scored.sort(key=lambda x: (x[1], -x[0]["win_count"]))
    return [c for c, _ in scored]


def _calc_avg_interval(results, current_draw):
    """平均出現間隔を計算"""
    if len(results) <= 1:
        return None

    draws = [r[0] for r in results]
    intervals = []

    for i in range(len(draws) - 1):
        intervals.append(draws[i + 1] - draws[i])

    # 最後の間隔（現在まで）
    intervals.append(current_draw - draws[-1])

    return sum(intervals) / len(intervals) if intervals else None


def run_full_simulation(conn):
    """全期間シミュレーション"""
    latest = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()[0]
    min_draw = conn.execute("SELECT MIN(draw_no) FROM draws").fetchone()[0]

    test_window = 50
    snapshot_interval = 50
    test_start = min(5000, min_draw + 500)
    test_end = latest - test_window

    methods = [
        ("標準ロジック", get_candidates_standard),
        ("短期トレンド優先", get_candidates_with_short_term_trend),
        ("クラスタリング検出", get_candidates_clustering_enhanced),
        ("短期⇔長期比較", get_candidates_short_long_intervals),
    ]

    results = {name: [] for name, _ in methods}

    print(f"シミュレーション実行中... (第{test_start}回～第{test_end}回)")

    for draw_no in range(test_start, test_end, snapshot_interval):
        test_results = conn.execute(
            "SELECT number FROM draws WHERE draw_no > ? AND draw_no <= ? ORDER BY draw_no",
            (draw_no, draw_no + test_window)
        ).fetchall()

        if not test_results:
            continue

        test_numbers = [r[0] for r in test_results]
        test_count = len(test_numbers)

        for name, method in methods:
            candidates = method(conn, draw_no, 2, 10)
            if not candidates:
                continue

            cand_set = {c["number"] for c in candidates}
            hits = sum(1 for num in test_numbers if num in cand_set)

            results[name].append({
                "hits": hits,
                "test": test_count,
                "candidates": len(cand_set),
            })

    # 結果集計
    print(f"\n=== シミュレーション結果 ===")
    print(f"テスト期間: 第{test_start}回～第{test_end}回")
    print(f"検証1回あたり: {test_window}回先まで")
    print(f"テスト回数: {len(results['標準ロジック'])}回\n")

    base_rate = None
    for name in ["標準ロジック", "短期トレンド優先", "クラスタリング検出", "短期⇔長期比較"]:
        res = results[name]
        if not res:
            continue

        total_tests = sum(r["test"] for r in res)
        total_hits = sum(r["hits"] for r in res)
        win_rate = total_hits / total_tests * 100

        avg_candidates = sum(r["candidates"] for r in res) / len(res)

        if name == "標準ロジック":
            base_rate = win_rate

        status = ""
        if name != "標準ロジック" and base_rate:
            improvement = (win_rate - base_rate) / base_rate * 100
            status = f"  [{improvement:+.1f}%]"

        print(f"{name:15} | 的中率: {win_rate:.2f}% ({total_hits:3}/{total_tests:4}) | 平均候補: {avg_candidates:.1f}個{status}")


if __name__ == "__main__":
    conn = connect()
    try:
        latest_draw = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()[0]
        min_draw = conn.execute("SELECT MIN(draw_no) FROM draws").fetchone()[0]

        print(f"\n=== ナンバーズ3 全期間シミュレーション ===")
        print(f"データ: 第{min_draw}回～第{latest_draw}回（計{latest_draw}回）\n")

        run_full_simulation(conn)

    finally:
        conn.close()
