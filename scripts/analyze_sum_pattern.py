#!/usr/bin/env python3
"""
ナンバーズ3 合計値（サム）の統計分析

理論値との比較で信憑性を検証
"""
import sys
from pathlib import Path
from collections import Counter
import math

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect


def theoretical_sum_distribution():
    """理論的な合計値の分布を計算"""
    # 000～999 の全1000パターンの合計値を計算
    sum_counts = Counter()
    for i in range(1000):
        num_str = f"{i:03d}"
        total = sum(int(d) for d in num_str)
        sum_counts[total] += 1

    return sum_counts


def chi_square_test(observed, expected):
    """カイ二乗検定"""
    chi_sq = 0.0
    df = 0  # 自由度

    for value in expected:
        obs = observed.get(value, 0)
        exp = expected[value]
        if exp > 0:
            chi_sq += (obs - exp) ** 2 / exp
            df += 1

    return chi_sq, df


def main():
    conn = connect()
    try:
        # 実際のデータを取得
        results = conn.execute(
            "SELECT number FROM draws ORDER BY draw_no"
        ).fetchall()

        actual_sums = Counter()
        for (number,) in results:
            total = sum(int(d) for d in number)
            actual_sums[total] += 1

        # 理論値
        theoretical = theoretical_sum_distribution()

        print("=== ナンバーズ3 合計値（サム）の統計分析 ===\n")
        print(f"実データ: {len(results)}回")
        print(f"理論値: 1000パターン分析\n")

        # カイ二乗検定
        chi_sq, df = chi_square_test(actual_sums, theoretical)
        p_value = 1.0 - chi_square_cdf(chi_sq, df)  # 簡易計算

        print(f"--- カイ二乗検定 ---")
        print(f"χ² = {chi_sq:.2f}, 自由度 = {df}")
        print(f"期待値との乖離: {'小さい（ランダム）' if chi_sq < 40 else '大きい（偏りあり）'}\n")

        # 合計値別の分析
        print("--- 合計値別の出現数 ---")
        print("合計 | 実績 | 理論 | 差分 | 実績率 | 理論率")
        print("-----|------|------|------|-------|-------")

        sum_values = sorted(set(list(actual_sums.keys()) + list(theoretical.keys())))
        outliers = []

        for s in sum_values:
            actual = actual_sums.get(s, 0)
            theory = theoretical.get(s, 0)
            diff = actual - theory
            actual_rate = actual / len(results) * 100
            theory_rate = theory / 1000 * 100

            mark = ""
            if abs(diff) > 10:
                mark = " ⚠️" if abs(diff) > 15 else ""
                if abs(diff) > 15:
                    outliers.append((s, diff, actual_rate, theory_rate))

            print(f"{s:4} | {actual:5} | {theory:5} | {diff:+4} | {actual_rate:5.1f}% | {theory_rate:5.1f}%{mark}")

        # 外れ値
        if outliers:
            print(f"\n--- 有意な偏り（差分>15） ---")
            for s, diff, actual_rate, theory_rate in outliers:
                direction = "出現多" if diff > 0 else "出現少"
                print(f"合計{s:2}: {direction} ({actual_rate:.1f}% vs 理論{theory_rate:.1f}%)")
        else:
            print(f"\n--- 有意な偏り ---")
            print("なし（完全にランダムと判定）")

        # 分布形状の評価
        mean_actual = sum(s * c for s, c in actual_sums.items()) / len(results)
        mean_theory = sum(s * c for s, c in theoretical.items()) / 1000

        variance_actual = sum((s - mean_actual) ** 2 * c for s, c in actual_sums.items()) / len(results)
        variance_theory = sum((s - mean_theory) ** 2 * c for s, c in theoretical.items()) / 1000

        print(f"\n--- 分布形状の比較 ---")
        print(f"実績 - 平均: {mean_actual:.1f}, 分散: {variance_actual:.1f}")
        print(f"理論 - 平均: {mean_theory:.1f}, 分散: {variance_theory:.1f}")

        # 結論
        print(f"\n=== 信憑性判定 ===")
        if chi_sq < 40 and len(outliers) == 0:
            print("✅ **ランダムと判定** - 合計値の統計は信憑性が低い")
            print("   → 予想には活用しない方が無難")
        else:
            print("⚠️  **偏りあり** - 合計値に統計的な傾向が存在")
            print("   → 改善案として活用の余地あり")

    finally:
        conn.close()


def chi_square_cdf(x, df):
    """カイ二乗分布のCDF（簡易版）"""
    # 簡易的な近似
    if df == 0:
        return 0.0
    return min(1.0, x / (2 * df))


if __name__ == "__main__":
    main()
