#!/usr/bin/env python3
"""
ピックアップロジック 要素分析

1. 平均間隔フィルタのみ（1桁だけ）
2. ストレート当選傾向のみ
3. 両方を組み合わせ（現在のロジック）

どれが最も有効か検証
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect


def get_all_numbers(conn, at_draw_no: int, min_count: int = 2):
    """全候補（フィルタなし）"""
    results = conn.execute(
        "SELECT DISTINCT number FROM draws WHERE draw_no <= ? ORDER BY number",
        (at_draw_no,)
    ).fetchall()
    return {r[0] for r in results}


def get_digit_candidates_only(conn, at_draw_no: int, min_count: int = 2):
    """平均間隔フィルタのみ（1桁の出現間隔）"""
    digit_data = conn.execute(
        """WITH digit_table AS (
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
           ),
           digit_stats AS (
             SELECT d, COUNT(*) as cnt, MAX(draw_no) as last_draw
             FROM digit_table GROUP BY d HAVING cnt >= ?
           )
           SELECT d FROM digit_stats ORDER BY d""",
        tuple([at_draw_no] * 10 + [min_count])
    ).fetchall()

    return {row[0] for row in digit_data}


def get_straight_candidates_only(conn, at_draw_no: int, min_count: int = 2):
    """ストレート当選傾向のみ"""
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
           WHERE nw.win_count >= ? AND (ng.avg_interval IS NULL OR ? - nw.last_win_draw_no >= ng.avg_interval)
           ORDER BY nw.number""",
        (at_draw_no, at_draw_no, at_draw_no, min_count, at_draw_no)
    ).fetchall()

    return {r[0] for r in results}


def get_combined_candidates(conn, at_draw_no: int, min_count: int = 2):
    """両方を組み合わせ（現在のロジック）"""
    digit_cands = get_digit_candidates_only(conn, at_draw_no, min_count)
    straight_cands = get_straight_candidates_only(conn, at_draw_no, min_count)

    # ストレート候補であり、かつ3桁すべてが1桁候補に含まれるもの
    combined = {
        num for num in straight_cands
        if all(ch in digit_cands for ch in num)
    }
    return combined


def run_comparison(conn):
    """全4つの方式を比較"""
    latest = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()[0]
    min_draw = conn.execute("SELECT MIN(draw_no) FROM draws").fetchone()[0]

    test_window = 50
    snapshot_interval = 50
    test_start = min(5000, min_draw + 500)
    test_end = latest - test_window

    methods = {
        "全候補（フィルタなし）": get_all_numbers,
        "1桁間隔のみ": get_digit_candidates_only,
        "ストレート傾向のみ": get_straight_candidates_only,
        "両方を組み合わせ（現在）": get_combined_candidates,
    }

    results = {name: [] for name in methods}

    print(f"比較実行中... (第{test_start}回～第{test_end}回)\n")

    for draw_no in range(test_start, test_end, snapshot_interval):
        test_results = conn.execute(
            "SELECT number FROM draws WHERE draw_no > ? AND draw_no <= ? ORDER BY draw_no",
            (draw_no, draw_no + test_window)
        ).fetchall()

        if not test_results:
            continue

        test_numbers = [r[0] for r in test_results]
        test_count = len(test_numbers)

        for name, method in methods.items():
            candidates = method(conn, draw_no, 2)
            hits = sum(1 for num in test_numbers if num in candidates)

            results[name].append({
                "hits": hits,
                "test": test_count,
                "candidates": len(candidates),
            })

    # 結果表示
    print("=== ピックアップロジック 要素別比較 ===\n")
    print(f"テスト期間: 第{test_start}回～第{test_end}回")
    print(f"テスト方式: 各時点から{test_window}回先までの当選を検証\n")

    results_list = []

    for name, res in results.items():
        if not res:
            continue

        total_tests = sum(r["test"] for r in res)
        total_hits = sum(r["hits"] for r in res)
        win_rate = total_hits / total_tests * 100
        avg_candidates = sum(r["candidates"] for r in res) / len(res)

        results_list.append({
            "name": name,
            "win_rate": win_rate,
            "hits": total_hits,
            "tests": total_tests,
            "avg_cands": avg_candidates,
        })

    # 成績の良い順にソート
    results_list.sort(key=lambda x: -x["win_rate"])

    base_rate = results_list[0]["win_rate"] if results_list else 0

    print("順位 | 方式                    | 的中率  | 的中  | 検証 | 平均候補 | 効率")
    print("-----|------------------------|--------|-------|------|----------|-------")

    for rank, result in enumerate(results_list, 1):
        efficiency = result["avg_cands"] * result["win_rate"]  # 候補数×的中率
        marker = "✅ 推奨" if rank == 1 else ""
        print(f" {rank:2} | {result['name']:24} | {result['win_rate']:6.2f}% | {result['hits']:5} | {result['tests']:4} | {result['avg_cands']:8.1f} | {efficiency:6.1f} {marker}")

    # 推奨理由の説明
    best = results_list[0]
    print(f"\n=== 推奨: {best['name']} ===")
    print(f"的中率: {best['win_rate']:.2f}%")
    print(f"平均候補数: {best['avg_cands']:.1f}個")
    print(f"理論値（0.1%）に対する倍率: {best['win_rate'] / 0.1:.1f}倍")

    # 各方式の詳細比較
    print(f"\n=== 各方式の詳細 ===\n")

    for result in results_list:
        ratio = result["avg_cands"] / 1000 * 100  # 候補数が全体のどれだけか
        print(f"【{result['name']}】")
        print(f"  的中率: {result['win_rate']:.2f}%")
        print(f"  的中数: {result['hits']}/{result['tests']}")
        print(f"  平均候補: {result['avg_cands']:.1f}個（全体の{ratio:.1f}%に絞り込み）")
        print(f"  効率: {result['avg_cands'] * result['win_rate']:.2f}")
        print()


if __name__ == "__main__":
    conn = connect()
    try:
        run_comparison(conn)
    finally:
        conn.close()
