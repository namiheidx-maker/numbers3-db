#!/usr/bin/env python3
"""
ナンバーズ3 手法別「理論値 vs 実績」検定。

予想サイトで使われる各手法（合計値・奇偶・大小・重複タイプ・ゾーン・桁別一様性・
引っ張り・スライド・ミラー・同桁一致・数字根）について、
全履歴の実績分布が「各桁が独立に一様ランダム」という理論分布と整合するかをカイ二乗検定で確認する。

理論分布は 000〜999 / 連続2回の全組合せ(10^6)を厳密に列挙して求める（近似式は使わない）。
注意: 検定は m 個を同時に行うため Bonferroni 補正（有意水準 0.05/m）で判定する。
      「有意」でも次回の当せん確率を示すものではなく、予測にはならない。
"""
from __future__ import annotations

import math
import sys
from collections import Counter
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ALPHA = 0.05
MIN_EXPECTED = 5.0  # カイ二乗検定の期待度数の下限（未満のビンは隣接ビンと併合）


# ---------- 統計関数（scipy非依存） ----------
def _gammainc_upper(a: float, x: float) -> float:
    """正則化上側不完全ガンマ関数 Q(a, x)。"""
    if x <= 0:
        return 1.0
    gln = math.lgamma(a)
    if x < a + 1:  # 級数展開
        ap, s, d = a, 1.0 / a, 1.0 / a
        for _ in range(10000):
            ap += 1
            d *= x / ap
            s += d
            if abs(d) < abs(s) * 1e-15:
                break
        return max(0.0, 1.0 - s * math.exp(-x + a * math.log(x) - gln))
    b = x + 1.0 - a  # 連分数展開
    c = 1.0 / 1e-300
    d = 1.0 / b
    h = d
    for i in range(1, 10000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return min(1.0, math.exp(-x + a * math.log(x) - gln) * h)


def chi2_sf(chi2: float, df: int) -> float:
    return _gammainc_upper(df / 2.0, chi2 / 2.0)


def merge_bins(labels, observed, probs, n):
    """期待度数が MIN_EXPECTED 未満のビンを隣接ビンに併合する。"""
    bins = [[[l], o, p] for l, o, p in zip(labels, observed, probs)]
    changed = True
    while changed and len(bins) > 2:
        changed = False
        for i, (_, _, p) in enumerate(bins):
            if p * n < MIN_EXPECTED:
                j = i + 1 if i + 1 < len(bins) else i - 1
                bins[j][0] = (bins[i][0] + bins[j][0]) if j > i else (bins[j][0] + bins[i][0])
                bins[j][1] += bins[i][1]
                bins[j][2] += bins[i][2]
                del bins[i]
                changed = True
                break
    out_labels = []
    for ls, _, _ in bins:
        out_labels.append(str(ls[0]) if len(ls) == 1 else f"{ls[0]}〜{ls[-1]}")
    return out_labels, [b[1] for b in bins], [b[2] for b in bins]


def make_test(name, note, labels, observed, probs, n):
    labels, observed, probs = merge_bins(labels, observed, probs, n)
    chi2 = sum((o - p * n) ** 2 / (p * n) for o, p in zip(observed, probs))
    df = len(observed) - 1
    return {
        "name": name, "note": note, "n": n, "chi2": chi2, "df": df,
        "p": chi2_sf(chi2, df),
        "rows": [
            {"label": l, "obs": o, "exp": p * n, "obs_pct": o / n * 100, "exp_pct": p * 100}
            for l, o, p in zip(labels, observed, probs)
        ],
    }


def dist_from_counter(theory: Counter, obs: Counter, keys=None):
    keys = sorted(theory) if keys is None else keys
    tot = sum(theory.values())
    return keys, [obs.get(k, 0) for k in keys], [theory[k] / tot for k in keys]


# ---------- 特徴量 ----------
def digits(num: str):
    return tuple(int(c) for c in num)


def f_sum(d): return sum(d)
def f_odd(d): return sum(x % 2 for x in d)
def f_big(d): return sum(1 for x in d if x >= 5)
def f_dup(d): return {3: "シングル", 2: "ダブル", 1: "トリプル"}[len(set(d))]
def f_root(d): return sum(d) % 10


def f_pull(cur, prev):  # 前回の数字集合に含まれる桁の数（引っ張り）
    s = set(prev)
    return sum(1 for x in cur if x in s)


def f_slide(cur, prev):  # 前回の数字±1(0↔9は循環)に一致する桁の数
    s = {(x + 1) % 10 for x in prev} | {(x - 1) % 10 for x in prev}
    return sum(1 for x in cur if x in s)


def f_mirror(cur, prev):  # ミラー数字(+5)に一致する桁の数
    s = {(x + 5) % 10 for x in prev}
    return sum(1 for x in cur if x in s)


def f_samepos(cur, prev):  # 同じ桁位置で前回と同じ数字
    return sum(1 for a, b in zip(cur, prev) if a == b)


ALL = [digits(f"{i:03d}") for i in range(1000)]


def theory_single(fn):
    return Counter(fn(d) for d in ALL)


def theory_pair(fn):
    """連続2回(前回, 今回)の全組合せ 10^6 を列挙。前回の数字の出方ごとにキャッシュして高速化。"""
    c = Counter()
    for prev in ALL:
        for cur in ALL:
            c[fn(cur, prev)] += 1
    return c


# ---------- 本体 ----------
def run(conn):
    rows = conn.execute("SELECT draw_no, number FROM draws ORDER BY draw_no").fetchall()
    nums = [(no, digits(str(n).zfill(3))) for no, n in rows]
    n = len(nums)
    tests = []

    def single(name, note, fn, keys=None):
        obs = Counter(fn(d) for _, d in nums)
        k, o, p = dist_from_counter(theory_single(fn), obs, keys)
        tests.append(make_test(name, note, k, o, p, n))

    single("合計値", "3桁の和（0〜27）。中央ほど組合せ数が多い", f_sum)
    single("合計値の下1桁（数字根）", "合計値の一の位（0〜9）", f_root)
    single("奇数の個数", "3桁中の奇数の数（0〜3）", f_odd)
    single("大数字(5〜9)の個数", "3桁中の大数字の数（0〜3）", f_big)
    single("重複タイプ", "シングル／ダブル／トリプル", f_dup, keys=["シングル", "ダブル", "トリプル"])

    # ゾーン: 各桁を 0-3 / 4-6 / 7-9 に分け、全桁をまとめて集計
    zone = lambda x: "0-3" if x <= 3 else ("4-6" if x <= 6 else "7-9")
    zobs = Counter(zone(x) for _, d in nums for x in d)
    zt = Counter({"0-3": 4, "4-6": 3, "7-9": 3})
    k, o, p = dist_from_counter(zt, zobs, ["0-3", "4-6", "7-9"])
    tests.append(make_test("エリア(ゾーン)分布", "各桁を 0-3 / 4-6 / 7-9 に分けて全桁で集計（理論 40/30/30%）", k, o, p, n * 3))

    # 桁別の一様性
    for pos, label in enumerate(["百の位", "十の位", "一の位"]):
        obs = Counter(d[pos] for _, d in nums)
        k, o, p = dist_from_counter(Counter({i: 1 for i in range(10)}), obs, list(range(10)))
        tests.append(make_test(f"{label}の一様性", "0〜9が各10%で出るか", k, o, p, n))

    # 前回との関係（連続する回のみ対象）
    pairs = [(nums[i][1], nums[i - 1][1]) for i in range(1, n) if nums[i][0] - nums[i - 1][0] == 1]
    m = len(pairs)
    for name, note, fn in [
        ("引っ張り", "今回の桁のうち、前回の数字集合に含まれる桁の数", f_pull),
        ("スライド(±1)", "今回の桁のうち、前回の数字±1に一致する桁の数", f_slide),
        ("ミラー(+5)", "今回の桁のうち、前回の数字の裏(0↔5,1↔6…)に一致する桁の数", f_mirror),
        ("同桁一致", "同じ桁位置で前回と同じ数字だった桁の数", f_samepos),
    ]:
        obs = Counter(fn(cur, prev) for cur, prev in pairs)
        k, o, p = dist_from_counter(theory_pair(fn), obs)
        tests.append(make_test(name, note, k, o, p, m))

    mtests = len(tests)
    threshold = ALPHA / mtests
    for t in tests:
        if t["p"] < threshold:
            t["verdict"], t["level"] = "有意（補正後）", 2
        elif t["p"] < ALPHA:
            t["verdict"], t["level"] = "補正前のみ有意", 1
        else:
            t["verdict"], t["level"] = "理論値の範囲内", 0
    return {"tests": tests, "n": n, "pairs": m, "m": mtests, "threshold": threshold}


def main():
    from db_common import connect
    conn = connect()
    try:
        res = run(conn)
    finally:
        conn.close()
    print(f"抽せん数 {res['n']}回 / 連続ペア {res['pairs']} / 検定数 {res['m']} / Bonferroni閾値 p<{res['threshold']:.4f}")
    for t in res["tests"]:
        print(f"\n■ {t['name']}  χ²={t['chi2']:.2f} df={t['df']} p={t['p']:.4f}  → {t['verdict']}")
        for r in t["rows"]:
            print(f"   {r['label']:>10}: 実績 {r['obs']:>5} ({r['obs_pct']:5.2f}%)  理論 {r['exp']:8.1f} ({r['exp_pct']:5.2f}%)")


if __name__ == "__main__":
    main()
