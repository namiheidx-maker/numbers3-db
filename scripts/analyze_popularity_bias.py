#!/usr/bin/env python3
"""
ナンバーズ3 人気数字と選ばれにくい数字の分析

人気バイアス：
1. 語呂合わせ（1+2+3=6「労働」、7+7+7=21「神秘」など）
2. ぞろ目（111, 222, 333...）
3. 連番（123, 456, 789）
4. 特定の日付（誕生日月日など）
5. 大吉数字（8は「末広がり」）
"""
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect


def is_popular(number: str):
    """人気の数字（バイアス）かどうか判定"""
    num = int(number)
    digits = [int(d) for d in number]

    # 1. ぞろ目
    if digits[0] == digits[1] == digits[2]:
        return True, "ぞろ目"

    # 2. 連番（昇順・降順）
    if (digits[0] + 1 == digits[1] and digits[1] + 1 == digits[2]) or \
       (digits[0] - 1 == digits[1] and digits[1] - 1 == digits[2]):
        return True, "連番"

    # 3. 大吉数字（8を含む、または合計が8, 18, 28）
    digit_sum = sum(digits)
    if 8 in digits or digit_sum in [8, 18, 28]:
        return True, "大吉数字"

    # 4. 特定の日付を意識した数字
    # 月日の組み合わせ（0101～1231）
    if number[0:2] in ['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']:
        month = int(number[0:2])
        day = int(number[2])
        if 1 <= month <= 12 and 1 <= day <= 9:
            return True, "月日パターン"

    # 5. 「123」型の見た目の美しい数字
    if number in ['012', '013', '014', '015', '023', '024', '025', '034', '035', '045',
                  '123', '124', '125', '134', '135', '145', '234', '235', '245', '345',
                  '567', '568', '569', '578', '579', '589', '678', '679', '689', '789']:
        return True, "見た目の美しさ"

    return False, None


def analyze_popularity(conn):
    """全期間の当選数字で人気バイアスを分析"""
    all_results = conn.execute(
        "SELECT number FROM draws ORDER BY draw_no"
    ).fetchall()

    popular_wins = Counter()
    unpopular_wins = Counter()
    popular_list = []
    unpopular_list = []

    for (number,) in all_results:
        is_pop, reason = is_popular(number)
        if is_pop:
            popular_wins[reason] += 1
            popular_list.append(number)
        else:
            unpopular_list.append(number)

    total = len(all_results)
    popular_count = len(popular_list)
    unpopular_count = len(unpopular_list)

    print("=== ナンバーズ3 人気バイアス分析 ===\n")
    print(f"全当選数字: {total}回")
    print(f"人気数字（バイアス）: {popular_count}回 ({popular_count/total*100:.1f}%)")
    print(f"選ばれにくい数字: {unpopular_count}回 ({unpopular_count/total*100:.1f}%)\n")

    print("--- 人気バイアスの内訳 ---")
    for reason, count in popular_wins.most_common():
        print(f"{reason:12}: {count:4}回 ({count/total*100:5.1f}%)")

    # 配当への影響を説明
    print("\n--- 配当への影響 ---")
    print(f"人気数字を選ぶと: 当選者が多い → 配当が低い")
    print(f"選ばれにくい数字: 当選者が少ない → 配当が高い")

    # ストレート傾向候補の中での人気度を分析
    latest = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()[0]

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
           SELECT nw.number
           FROM num_wins nw
           LEFT JOIN num_gaps ng ON nw.number = ng.number
           WHERE nw.win_count >= 2 AND (ng.avg_interval IS NULL OR ? - nw.last_win_draw_no >= ng.avg_interval)
           LIMIT 100""",
        (latest, latest, latest, latest)
    ).fetchall()

    candidates_set = {r[0] for r in candidates}

    popular_cands = [c for c in candidates_set if is_popular(c)[0]]
    unpopular_cands = [c for c in candidates_set if not is_popular(c)[0]]

    print(f"\n--- 現在のストレート傾向候補（100個）の構成 ---")
    print(f"人気数字: {len(popular_cands)}個 ({len(popular_cands)/len(candidates_set)*100:.1f}%)")
    print(f"  例: {sorted(popular_cands)[:10]}")
    print(f"選ばれにくい数字: {len(unpopular_cands)}個 ({len(unpopular_cands)/len(candidates_set)*100:.1f}%)")
    print(f"  例: {sorted(unpopular_cands)[:10]}")

    print(f"\n--- 推奨 ---")
    print(f"人気数字を除外して購入すれば、")
    print(f"同じ的中率でも配当が高くなる可能性があります。")
    print(f"除外候補: {len(popular_cands)}個")


if __name__ == "__main__":
    conn = connect()
    try:
        analyze_popularity(conn)
    finally:
        conn.close()
