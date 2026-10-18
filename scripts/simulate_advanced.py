#!/usr/bin/env python3
"""
ナンバーズ3 ピックアップロジック 高度なシミュレーション＋改善案の検証

改善案：
1. 複数の時間窓（短期vs長期）での平均間隔の比較
2. クラスタリングパターンの検出
3. ボックス当選傾向の追加フィルタ
4. 指数加重平均で最近のデータを重視
"""
import sys
from pathlib import Path
from collections import defaultdict, deque

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect


def get_candidates_standard(conn, at_draw_no: int, min_count: int = 2, top: int = 10):
    """標準ロジック（既存）"""
    straight_rows = conn.execute(
        """WITH num_wins AS (
             SELECT number, COUNT(*) as win_count, MAX(draw_date) as last_win_date, MAX(draw_no) as last_win_draw_no
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
           SELECT nw.number, nw.win_count, nw.last_win_date, nw.last_win_draw_no, ng.avg_interval
           FROM num_wins nw
           LEFT JOIN num_gaps ng ON nw.number = ng.number
           WHERE nw.win_count >= ?
           ORDER BY nw.win_count DESC, nw.last_win_draw_no ASC""",
        (at_draw_no, at_draw_no, at_draw_no, min_count)
    ).fetchall()

    digit_rows = conn.execute(
        """WITH digits AS (
             SELECT d, draw_no FROM (
               SELECT '0' as d, draw_no FROM draws WHERE draw_no <= ? AND (number LIKE '0%' OR number LIKE '%0%' OR number LIKE '%0')
               UNION ALL SELECT '1', draw_no FROM draws WHERE draw_no <= ? AND (number LIKE '1%' OR number LIKE '%1%' OR number LIKE '%1')
               UNION ALL SELECT '2', draw_no FROM draws WHERE draw_no <= ? AND (number LIKE '2%' OR number LIKE '%2%' OR number LIKE '%2')
               UNION ALL SELECT '3', draw_no FROM draws WHERE draw_no <= ? AND (number LIKE '3%' OR number LIKE '%3%' OR number LIKE '%3')
               UNION ALL SELECT '4', draw_no FROM draws WHERE draw_no <= ? AND (number LIKE '4%' OR number LIKE '%4%' OR number LIKE '%4')
               UNION ALL SELECT '5', draw_no FROM draws WHERE draw_no <= ? AND (number LIKE '5%' OR number LIKE '%5%' OR number LIKE '%5')
               UNION ALL SELECT '6', draw_no FROM draws WHERE draw_no <= ? AND (number LIKE '6%' OR number LIKE '%6%' OR number LIKE '%6')
               UNION ALL SELECT '7', draw_no FROM draws WHERE draw_no <= ? AND (number LIKE '7%' OR number LIKE '%7%' OR number LIKE '%7')
               UNION ALL SELECT '8', draw_no FROM draws WHERE draw_no <= ? AND (number LIKE '8%' OR number LIKE '%8%' OR number LIKE '%8')
               UNION ALL SELECT '9', draw_no FROM draws WHERE draw_no <= ? AND (number LIKE '9%' OR number LIKE '%9%' OR number LIKE '%9')
             )
           )
           SELECT d, COUNT(*) as cnt, MAX(draw_no) as last_draw
           FROM digits GROUP BY d HAVING cnt >= ?
           ORDER BY cnt DESC""",
        tuple([at_draw_no] * 10 + [min_count])
    ).fetchall()

    digit_candidates = set()
    for digit, win_count, last_draw in digit_rows:
        if last_draw is None:
            digit_candidates.add(digit)
        else:
            draws_elapsed = at_draw_no - last_draw
            avg_interval = win_count / (at_draw_no - (conn.execute("SELECT MIN(draw_no) FROM draws").fetchone()[0] - 1))
            if draws_elapsed >= avg_interval:
                digit_candidates.add(digit)

    matched = []
    for number, win_count, last_win_date, last_win_draw_no, avg_interval in straight_rows:
        if avg_interval is None:
            passes = True
        else:
            draws_elapsed = at_draw_no - last_win_draw_no
            passes = draws_elapsed >= avg_interval

        if passes and all(ch in digit_candidates for ch in str(number)):
            matched.append({"number": str(number), "win_count": win_count, "last_draw": last_win_draw_no})

    return matched[:top]


def get_clustering_score(conn, at_draw_no: int, number: str, window: int = 20):
    """クラスタリングスコア：同じ数字が最近出現しやすいか"""
    recent = conn.execute(
        "SELECT COUNT(*) FROM draws WHERE draw_no > ? AND draw_no <= ? AND number = ?",
        (at_draw_no - window, at_draw_no, number)
    ).fetchone()[0]

    long_term = conn.execute(
        "SELECT COUNT(*) FROM draws WHERE draw_no <= ? AND number = ?",
        (at_draw_no, number)
    ).fetchone()[0]

    if long_term == 0:
        return 0.0

    return (recent / window) / (long_term / at_draw_no)


def get_box_tendency_score(conn, at_draw_no: int, number: str, min_count: int = 2):
    """ボックス当選傾向スコア"""
    box_key = "".join(sorted(number))

    box_count = conn.execute(
        "SELECT COUNT(*) FROM draws WHERE draw_no <= ? AND box_key = ?",
        (at_draw_no, box_key)
    ).fetchone()[0]

    if box_count < min_count:
        return 0.0

    return box_count / at_draw_no


def exponential_weighted_avg(conn, at_draw_no: int, number: str, lambda_: float = 0.95):
    """指数加重平均: 最近のデータをより重視"""
    results = conn.execute(
        "SELECT draw_no FROM draws WHERE draw_no <= ? AND number = ? ORDER BY draw_no DESC LIMIT 10",
        (at_draw_no, number)
    ).fetchall()

    if not results:
        return None

    intervals = []
    prev_draw = at_draw_no
    for (draw_no,) in results:
        intervals.append(prev_draw - draw_no)
        prev_draw = draw_no

    # 指数加重平均
    weighted_sum = 0.0
    weight_sum = 0.0
    for i, interval in enumerate(intervals):
        weight = (lambda_ ** i)
        weighted_sum += interval * weight
        weight_sum += weight

    return weighted_sum / weight_sum if weight_sum > 0 else None


def run_simulation(conn, test_start: int, test_end: int, test_window: int = 50,
                   snapshot_interval: int = 50, top: int = 10, min_count: int = 2):
    """メインシミュレーション"""
    results_standard = []
    results_with_clustering = []
    results_with_box = []
    results_with_exponential = []

    for draw_no in range(test_start, test_end, snapshot_interval):
        # 標準ロジック
        candidates_std = get_candidates_standard(conn, draw_no, min_count, top)
        if not candidates_std:
            continue

        std_set = {c["number"] for c in candidates_std}

        # クラスタリング対応版（スコアが高いもののみ）
        candidates_clustering = [c for c in candidates_std if get_clustering_score(conn, draw_no, c["number"]) > 0.5]
        clustering_set = {c["number"] for c in candidates_clustering} if candidates_clustering else std_set

        # ボックス対応版（スコアが高いもののみ）
        candidates_box = [c for c in candidates_std if get_box_tendency_score(conn, draw_no, c["number"], min_count) > 0.002]
        box_set = {c["number"] for c in candidates_box} if candidates_box else std_set

        # 指数加重平均版
        candidates_exp = []
        for c in candidates_std:
            exp_avg = exponential_weighted_avg(conn, draw_no, c["number"])
            if exp_avg is None:
                candidates_exp.append(c)
            else:
                curr_draw = draw_no - c["last_draw"]
                if curr_draw >= exp_avg:
                    candidates_exp.append(c)
        exp_set = {c["number"] for c in candidates_exp} if candidates_exp else std_set

        # テストデータの取得
        test_results = conn.execute(
            "SELECT number FROM draws WHERE draw_no > ? AND draw_no <= ? ORDER BY draw_no",
            (draw_no, draw_no + test_window)
        ).fetchall()

        if not test_results:
            continue

        test_numbers = [r[0] for r in test_results]

        # 各方式での的中数を計算
        hits_std = sum(1 for num in test_numbers if num in std_set)
        hits_clustering = sum(1 for num in test_numbers if num in clustering_set)
        hits_box = sum(1 for num in test_numbers if num in box_set)
        hits_exp = sum(1 for num in test_numbers if num in exp_set)

        test_count = len(test_numbers)

        results_standard.append({"hits": hits_std, "test": test_count, "candidates": len(std_set)})
        results_with_clustering.append({"hits": hits_clustering, "test": test_count, "candidates": len(clustering_set)})
        results_with_box.append({"hits": hits_box, "test": test_count, "candidates": len(box_set)})
        results_with_exponential.append({"hits": hits_exp, "test": test_count, "candidates": len(exp_set)})

    return results_standard, results_with_clustering, results_with_box, results_with_exponential


def print_results(name: str, results: list):
    """結果を表示"""
    if not results:
        print(f"{name}: データなし")
        return

    total_tests = sum(r["test"] for r in results)
    total_hits = sum(r["hits"] for r in results)
    win_rate = total_hits / total_tests * 100 if total_tests else 0.0
    avg_candidates = sum(r["candidates"] for r in results) / len(results)

    print(f"{name}:")
    print(f"  的中率: {win_rate:.2f}% ({total_hits}/{total_tests})")
    print(f"  平均候補数: {avg_candidates:.1f}個")
    print(f"  テスト数: {len(results)}回")


def main():
    conn = connect()
    try:
        latest_draw = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()[0]
        min_draw = conn.execute("SELECT MIN(draw_no) FROM draws").fetchone()[0]

        print(f"\n=== ナンバーズ3 大規模シミュレーション（全期間） ===")
        print(f"データ範囲: 第{min_draw}回～第{latest_draw}回（総{latest_draw}回）\n")

        # テスト期間を最大化
        test_window = 50
        snapshot_interval = 50
        test_start = min(5000, min_draw + 500)
        test_end = latest_draw - test_window

        print(f"テスト設定: {test_window}回先まで検証、{snapshot_interval}回ごとにスナップショット")
        print(f"テスト範囲: 第{test_start}回～第{test_end}回\n")

        results_std, results_cluster, results_box, results_exp = run_simulation(
            conn, test_start, test_end, test_window, snapshot_interval
        )

        print("=== 各方式の的中率比較 ===\n")
        print_results("【基準】標準ロジック（平均間隔フィルタ）", results_std)
        print()
        print_results("【改善1】+ クラスタリング検出", results_cluster)
        print()
        print_results("【改善2】+ ボックス当選傾向フィルタ", results_box)
        print()
        print_results("【改善3】+ 指数加重平均", results_exp)

        # 改善効果の計算
        if results_std:
            base_rate = sum(r["hits"] for r in results_std) / sum(r["test"] for r in results_std) * 100

            print(f"\n=== 改善効果（基準: {base_rate:.2f}%） ===")
            for name, results in [
                ("クラスタリング", results_cluster),
                ("ボックス傾向", results_box),
                ("指数加重平均", results_exp),
            ]:
                if results:
                    rate = sum(r["hits"] for r in results) / sum(r["test"] for r in results) * 100
                    improvement = (rate - base_rate) / base_rate * 100
                    print(f"{name}: {rate:.2f}% ({improvement:+.1f}%)")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
