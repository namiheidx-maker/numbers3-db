#!/usr/bin/env python3
"""
ナンバーズ3 ピックアップロジックの過去シミュレーション。

考え方:
  1. 過去のある時点（draw_no = N）での候補を計算
  2. その後の N+1 ～ N+M 回の実際の当選結果が
     その時点での候補に含まれているか確認
  3. 当選率を集計

例：
  draw_no=6900 時点での候補を計算
  → 6901～6950 回の実際の当選がその候補に何回含まれるか
"""
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect
from predict import get_pickup_candidates, MIN_COUNT_FOR_INTERVAL


def simulate(conn, test_draw_start: int, test_draw_count: int, top: int = 10, min_count: int = MIN_COUNT_FOR_INTERVAL):
    """
    test_draw_start 時点でのピックアップ候補を計算し、
    その後の test_draw_count 回の当選結果で検証する。

    戻り値: (直中, 外れた回数, 候補に含まれた数字リスト)
    """
    # test_draw_start 時点での DB スナップショットを取得
    # ※ SQL の WHERE draw_no <= test_draw_start で時点を遡る

    # 候補を計算する際の「現時点」を test_draw_start に制限
    latest_before = conn.execute(
        f"SELECT MAX(draw_no) FROM draws WHERE draw_no <= ?",
        (test_draw_start,)
    ).fetchone()[0]

    if latest_before is None:
        return None  # テスト開始時点に十分なデータがない

    # get_pickup_candidates の時点バージョンが必要 → 以下で手作業実装
    matched = _get_pickup_candidates_at_draw(conn, test_draw_start, min_count, top)

    if not matched:
        return None  # その時点では候補なし

    # 候補の数字セット
    candidate_numbers = {e["key"] for e in matched}

    # その後の test_draw_count 回のデータ
    test_draw_range = (test_draw_start + 1, test_draw_start + test_draw_count)
    results = conn.execute(
        """SELECT draw_no, number FROM draws
           WHERE draw_no > ? AND draw_no <= ?
           ORDER BY draw_no""",
        test_draw_range
    ).fetchall()

    hits = 0
    hits_list = []
    for draw_no, number in results:
        if number in candidate_numbers:
            hits += 1
            hits_list.append((draw_no, number))

    return {
        "snapshot_draw": test_draw_start,
        "candidate_count": len(matched),
        "candidates": candidate_numbers,
        "test_draws": len(results),
        "hits": hits,
        "miss": len(results) - hits,
        "hits_list": hits_list,
        "win_rate": hits / len(results) * 100 if results else 0.0,
    }


def _get_pickup_candidates_at_draw(conn, at_draw_no: int, min_count: int, top: int):
    """指定時点でのピックアップ候補を取得（その時点までのデータのみを使用）"""

    # ストレート（3桁）の統計: draw_no <= at_draw_no のデータのみ
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

    # 1桁の統計
    digit_rows = conn.execute(
        """WITH d0 AS (
             SELECT '0' as digit, COUNT(*) as cnt, MAX(draw_no) as last_draw FROM draws WHERE draw_no <= ?
               AND (number LIKE '0%' OR number LIKE '%0%' OR number LIKE '%0')
           ),
           d1 AS (
             SELECT '1' as digit, COUNT(*) as cnt, MAX(draw_no) as last_draw FROM draws WHERE draw_no <= ?
               AND (number LIKE '1%' OR number LIKE '%1%' OR number LIKE '%1')
           ),
           d2 AS (
             SELECT '2' as digit, COUNT(*) as cnt, MAX(draw_no) as last_draw FROM draws WHERE draw_no <= ?
               AND (number LIKE '2%' OR number LIKE '%2%' OR number LIKE '%2')
           ),
           d3 AS (
             SELECT '3' as digit, COUNT(*) as cnt, MAX(draw_no) as last_draw FROM draws WHERE draw_no <= ?
               AND (number LIKE '3%' OR number LIKE '%3%' OR number LIKE '%3')
           ),
           d4 AS (
             SELECT '4' as digit, COUNT(*) as cnt, MAX(draw_no) as last_draw FROM draws WHERE draw_no <= ?
               AND (number LIKE '4%' OR number LIKE '%4%' OR number LIKE '%4')
           ),
           d5 AS (
             SELECT '5' as digit, COUNT(*) as cnt, MAX(draw_no) as last_draw FROM draws WHERE draw_no <= ?
               AND (number LIKE '5%' OR number LIKE '%5%' OR number LIKE '%5')
           ),
           d6 AS (
             SELECT '6' as digit, COUNT(*) as cnt, MAX(draw_no) as last_draw FROM draws WHERE draw_no <= ?
               AND (number LIKE '6%' OR number LIKE '%6%' OR number LIKE '%6')
           ),
           d7 AS (
             SELECT '7' as digit, COUNT(*) as cnt, MAX(draw_no) as last_draw FROM draws WHERE draw_no <= ?
               AND (number LIKE '7%' OR number LIKE '%7%' OR number LIKE '%7')
           ),
           d8 AS (
             SELECT '8' as digit, COUNT(*) as cnt, MAX(draw_no) as last_draw FROM draws WHERE draw_no <= ?
               AND (number LIKE '8%' OR number LIKE '%8%' OR number LIKE '%8')
           ),
           d9 AS (
             SELECT '9' as digit, COUNT(*) as cnt, MAX(draw_no) as last_draw FROM draws WHERE draw_no <= ?
               AND (number LIKE '9%' OR number LIKE '%9%' OR number LIKE '%9')
           ),
           all_digits AS (
             SELECT * FROM d0 UNION ALL SELECT * FROM d1 UNION ALL SELECT * FROM d2 UNION ALL
             SELECT * FROM d3 UNION ALL SELECT * FROM d4 UNION ALL SELECT * FROM d5 UNION ALL
             SELECT * FROM d6 UNION ALL SELECT * FROM d7 UNION ALL SELECT * FROM d8 UNION ALL SELECT * FROM d9
           )
           SELECT digit, cnt as win_count,
                  CAST(? - (SELECT MIN(draw_no) FROM draws) AS FLOAT) / NULLIF(cnt, 1) as avg_interval,
                  last_draw
           FROM all_digits
           WHERE cnt >= ?
           ORDER BY cnt DESC""",
        tuple([at_draw_no] * 10 + [at_draw_no, min_count])
    ).fetchall()

    # 1桁の候補を判定
    digit_candidates = set()
    for digit, win_count, avg_interval, last_draw in digit_rows:
        if avg_interval is None:
            digit_candidates.add(digit)
        else:
            draws_elapsed = at_draw_no - last_draw
            if draws_elapsed >= avg_interval:
                digit_candidates.add(digit)

    # ストレートの候補を判定
    matched = []
    for number, win_count, last_win_date, last_win_draw_no, avg_interval in straight_rows:
        if avg_interval is None:
            passes_straight = True
        else:
            draws_elapsed = at_draw_no - last_win_draw_no
            passes_straight = draws_elapsed >= avg_interval

        if passes_straight:
            if all(ch in digit_candidates for ch in str(number)):
                matched.append({
                    "key": str(number),
                    "win_count": win_count,
                    "last_win_date": last_win_date,
                    "last_win_draw_no": last_win_draw_no,
                    "avg_interval": avg_interval,
                    "draws_elapsed": at_draw_no - last_win_draw_no,
                })

    matched.sort(key=lambda e: (-e["win_count"], e["last_win_draw_no"]))
    return matched[:top]


def main():
    conn = connect()
    try:
        latest_draw = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()[0]

        print(f"\n=== ナンバーズ3 ピックアップロジック 過去シミュレーション ===")
        print(f"現在のデータ: 第1回～第{latest_draw}回（総{latest_draw}回）\n")

        # シミュレーション設定
        test_window = 50  # 各時点から 50 回先までをテスト
        snapshot_interval = 50  # 50回ごとにスナップショット（より細かく）
        top = 10
        min_count = 2

        # テスト開始点 - 早めのスタートでより多くのサンプルを取得
        test_start = 6500
        test_end = latest_draw - test_window

        print(f"設定: 毎{snapshot_interval}回ごとにピックアップ候補を計算し、その後{test_window}回の当選を検証")
        print(f"テスト範囲: 第{test_start}回～第{test_end}回の時点でスナップショット\n")

        results = []
        for draw_no in range(test_start, test_end, snapshot_interval):
            try:
                result = simulate(conn, draw_no, test_window, top, min_count)
                if result:
                    results.append(result)
                    print(f"第{result['snapshot_draw']}回時点（候補{result['candidate_count']}個）→ 検証{result['test_draws']}回: "
                          f"的中 {result['hits']}回 / 外れ {result['miss']}回 / 的中率 {result['win_rate']:.1f}%")
            except Exception as e:
                print(f"エラー（第{draw_no}回時点）: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc()

        if not results:
            print("シミュレーション実行失敗（候補が見つかりませんでした）")
            return

        # 統計集計
        total_tests = sum(r["test_draws"] for r in results)
        total_hits = sum(r["hits"] for r in results)
        avg_win_rate = total_hits / total_tests * 100 if total_tests > 0 else 0.0

        print(f"\n=== 集計結果 ===")
        print(f"テスト回数: {len(results)}回")
        print(f"総検証試合数: {total_tests}回")
        print(f"総的中数: {total_hits}回")
        print(f"総的中率: {avg_win_rate:.2f}%")
        print(f"平均的中率（各時点の平均）: {sum(r['win_rate'] for r in results) / len(results):.2f}%")

        # 内訳表示
        print(f"\n=== 当選パターン（サンプル表示：最初の5時点分） ===")
        for result in results[:5]:
            print(f"\n第{result['snapshot_draw']}回時点での候補: {sorted(result['candidates'])}")
            hits_str = ", ".join([f"第{d}回={n}" for d, n in result['hits_list']])
            print(f"その後{result['test_draws']}回での的中: {hits_str}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
