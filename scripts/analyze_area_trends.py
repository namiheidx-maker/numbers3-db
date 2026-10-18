#!/usr/bin/env python3
"""
ナンバーズ3 エリア分析
- 数字を4つのエリアに分割：0（外れ値）、1-333、334-666、667-999
- 直近の出現傾向を分析して、推奨エリアを判定
"""
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect


def classify_area(number: str) -> str:
    """3桁の数字をエリアに分類"""
    num = int(number)
    if num == 0:
        return "0"
    elif 1 <= num <= 333:
        return "1-333"
    elif 334 <= num <= 666:
        return "334-666"
    else:  # 667-999
        return "667-999"


def analyze_area_trends(conn):
    """エリア分析"""
    # 当選数字を時系列で取得
    draws = conn.execute(
        "SELECT draw_no, number FROM draws ORDER BY draw_no"
    ).fetchall()

    if not draws:
        print("データがありません")
        return

    latest_draw_no = draws[-1][0]
    total_count = len(draws)

    # エリアに分類
    area_draws = {
        "0": [],
        "1-333": [],
        "334-666": [],
        "667-999": [],
    }

    for draw_no, number in draws:
        area = classify_area(number)
        area_draws[area].append((draw_no, number))

    print("=== ナンバーズ3 エリア分析 ===\n")

    # 全期間統計
    print("【全期間】")
    for area in ["0", "1-333", "334-666", "667-999"]:
        count = len(area_draws[area])
        pct = count / total_count * 100
        print(f"  {area:9}: {count:4}回 ({pct:5.1f}%)")

    # 直近分析
    periods = {
        "直近30回": max(0, total_count - 30),
        "直近50回": max(0, total_count - 50),
        "直近100回": max(0, total_count - 100),
    }

    for period_name, start_idx in periods.items():
        period_draws = draws[start_idx:]
        period_total = len(period_draws)

        print(f"\n【{period_name}】")
        area_counts = Counter(classify_area(num) for _, num in period_draws)

        for area in ["0", "1-333", "334-666", "667-999"]:
            count = area_counts.get(area, 0)
            pct = count / period_total * 100 if period_total > 0 else 0
            print(f"  {area:9}: {count:2}回 ({pct:5.1f}%)")

        # 推奨判定（0を除外）
        active_areas = {
            area: area_counts.get(area, 0)
            for area in ["1-333", "334-666", "667-999"]
        }

        if active_areas:
            recommended = max(active_areas, key=active_areas.get)
            rec_pct = active_areas[recommended] / period_total * 100
            print(f"\n  💡 推奨エリア: {recommended} ({rec_pct:.1f}%)")

    # インサイト
    print("\n=== インサイト ===")
    recent_100 = draws[max(0, total_count - 100):]
    recent_area_counts = Counter(classify_area(num) for _, num in recent_100)
    all_area_counts = Counter(classify_area(num) for _, num in draws)

    print("\n【エリア出現の偏り（直近100回 vs 全期間）】")
    for area in ["1-333", "334-666", "667-999"]:
        recent_pct = recent_area_counts.get(area, 0) / len(recent_100) * 100
        all_pct = all_area_counts.get(area, 0) / total_count * 100
        diff = recent_pct - all_pct

        trend = "📈 増加傾向" if diff > 5 else "📉 減少傾向" if diff < -5 else "➡️ 安定"
        print(f"  {area:9}: {all_pct:5.1f}% → {recent_pct:5.1f}% ({diff:+.1f}pt) {trend}")

    # エリア0の分析
    area_0_count = len(area_draws["0"])
    area_0_pct = area_0_count / total_count * 100
    print(f"\n【エリア0（0）の出現】")
    print(f"  全期間: {area_0_count}回 ({area_0_pct:.1f}%)")
    print(f"  → 「0」が出た回は戦略外（外れ値として無視）")


if __name__ == "__main__":
    conn = connect()
    try:
        analyze_area_trends(conn)
    finally:
        conn.close()
