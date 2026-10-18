#!/usr/bin/env python3
"""ピックアップロジックの詳細シミュレーション分析"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect
from simulate_historical import _get_pickup_candidates_at_draw


def detailed_analysis(conn, min_count: int = 2, top: int = 10):
    """より詳細な分析を実行"""
    latest_draw = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()[0]

    print("=== ナンバーズ3 ピックアップロジック 詳細シミュレーション分析 ===\n")

    test_window = 50
    test_start = 6500
    test_end = latest_draw - test_window

    # 候補個数別の統計
    by_candidate_count = {}
    all_results = []

    for draw_no in range(test_start, test_end, 50):
        matched = _get_pickup_candidates_at_draw(conn, draw_no, min_count, top)
        candidate_count = len(matched)

        if not matched:
            continue

        candidate_set = {e["key"] for e in matched}

        # 次の50回で的中を確認
        results = conn.execute(
            "SELECT draw_no, number FROM draws WHERE draw_no > ? AND draw_no <= ? ORDER BY draw_no",
            (draw_no, draw_no + test_window)
        ).fetchall()

        hits = sum(1 for _, num in results if num in candidate_set)

        # 統計データの記録
        all_results.append({
            "snapshot_draw": draw_no,
            "candidate_count": candidate_count,
            "test_count": len(results),
            "hits": hits,
            "win_rate": hits / len(results) * 100 if results else 0.0,
            "candidates": candidate_set,
        })

        if candidate_count not in by_candidate_count:
            by_candidate_count[candidate_count] = {"hits": 0, "total": 0}
        by_candidate_count[candidate_count]["total"] += len(results)
        by_candidate_count[candidate_count]["hits"] += hits

    # 全体統計
    total_tests = sum(r["test_count"] for r in all_results)
    total_hits = sum(r["hits"] for r in all_results)
    total_win_rate = total_hits / total_tests * 100 if total_tests else 0.0

    print(f"テスト数: {len(all_results)}回")
    print(f"総検証試合: {total_tests}回")
    print(f"総的中: {total_hits}回")
    print(f"**総的中率: {total_win_rate:.2f}%**\n")

    # 候補個数別の分析
    print("--- 候補個数別の的中率 ---")
    print("候補数 | 検証回 | 的中 | 的中率 | 1回あたり期待値")
    print("-------|--------|------|-------|---------------")

    for cand_count in sorted(by_candidate_count.keys()):
        stats = by_candidate_count[cand_count]
        total = stats["total"]
        hits = stats["hits"]
        rate = hits / total * 100 if total else 0.0
        expected_per_draw = 1 / 1000 * cand_count * 100  # 理論値
        print(f"{cand_count:6} | {total:6} | {hits:4} | {rate:5.1f}% | {expected_per_draw:5.2f}%")

    # 候補個数の分布
    print(f"\n--- 候補個数の分布 ---")
    avg_candidates = sum(r["candidate_count"] for r in all_results) / len(all_results)
    print(f"平均候補数: {avg_candidates:.1f}個")
    print(f"最小候補数: {min(r['candidate_count'] for r in all_results)}個")
    print(f"最大候補数: {max(r['candidate_count'] for r in all_results)}個")

    # 理論値との比較
    print(f"\n--- 理論値との比較 ---")
    print(f"ナンバーズ3ストレート当選確率（理論値）: 0.1% (1/1000)")
    print(f"このロジックの的中率: {total_win_rate:.2f}%")
    print(f"理論値に対する倍率: {total_win_rate / 0.1:.1f}倍")

    avg_expected = (1 / 1000 * avg_candidates) * 100
    print(f"\n平均候補数({avg_candidates:.1f}個)での理論的期待値: {avg_expected:.2f}%")
    print(f"実際の的中率 / 期待値: {total_win_rate / avg_expected:.1f}倍")

    # 当選実例（詳細）
    print(f"\n--- 当選実例（全{total_hits}件） ---")
    for i, result in enumerate(all_results, 1):
        if result["hits"] > 0:
            draws_info = conn.execute(
                "SELECT draw_no, number FROM draws WHERE draw_no > ? AND draw_no <= ? AND number IN ({})".format(
                    ",".join("?" * len(result["candidates"]))
                ),
                [result["snapshot_draw"], result["snapshot_draw"] + test_window] + list(result["candidates"])
            ).fetchall()
            print(f"\n{i}. 第{result['snapshot_draw']}回時点の候補（{result['candidate_count']}個）から")
            for draw_no, num in draws_info:
                print(f"   第{draw_no}回: {num} ✓")


if __name__ == "__main__":
    conn = connect()
    try:
        detailed_analysis(conn)
    finally:
        conn.close()
