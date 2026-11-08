#!/usr/bin/env python3
"""
ナンバーズ3 「一時的な偏りは続くか」ウォークフォワード検証。

窓（直近W回）で見えた桁別の偏り（ホット/コールド）が、次の回・次の窓に持続するかを検証する。
  A. ホット/コールド的中率: 各時点で直近W回に最多/最少で出た数字を、桁位置ごとに選び、次回の同じ桁がそれと一致する率
     （理論値10%。選び方は過去のみに依存するので、各回の結果は独立・厳密に二項分布）
  B. 偏りの持続性: 連続する2つの非重複ブロックで、各数字のz値を相関（理論値0）
  C. 参考: 非重複ブロックのうち「一時的な偏り(χ²検定 p<0.05)」が見えた割合（偶然でも約5%出る）
検定は同時に複数行うので Bonferroni 補正で判定する。
"""
from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from theory_vs_actual import chi2_sf, ALPHA

WINDOWS = (30, 50, 100, 200)
POS_LABELS = ("百の位", "十の位", "一の位")


def norm_two_sided_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def binom_test(hits: int, n: int, p0: float):
    """正規近似（n が数万のため十分）。戻り値: (z, p)"""
    z = (hits - n * p0) / math.sqrt(n * p0 * (1 - p0))
    return z, norm_two_sided_p(z)


def hot_cold_hits(seq, W):
    """各時点で直近W回の最多/最少の数字（同数は小さい数字を優先）を選び、次回の的中数を数える。"""
    counts = [0] * 10
    for x in seq[:W]:
        counts[x] += 1
    trials = hot = cold = 0
    for t in range(W, len(seq)):
        h = max(range(10), key=lambda d: (counts[d], -d))
        c = min(range(10), key=lambda d: (counts[d], d))
        nxt = seq[t]
        trials += 1
        hot += nxt == h
        cold += nxt == c
        counts[nxt] += 1
        counts[seq[t - W]] -= 1
    return trials, hot, cold


def block_counts(seq, W):
    return [Counter(seq[i:i + W]) for i in range(0, len(seq) - W + 1, W)]


def persistence(seqs, W):
    """連続ブロック間のz値相関 r と、正規近似の統計量 r*sqrt(n)。"""
    sd = math.sqrt(W * 0.1 * 0.9)
    xs, ys = [], []
    for seq in seqs:
        bc = block_counts(seq, W)
        for a, b in zip(bc, bc[1:]):
            for d in range(10):
                xs.append((a.get(d, 0) - W / 10) / sd)
                ys.append((b.get(d, 0) - W / 10) / sd)
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    r = sxy / math.sqrt(sxx * syy)
    return r, n, r * math.sqrt(n)


def significant_block_rate(seqs, W):
    sig = tot = 0
    for seq in seqs:
        for c in block_counts(seq, W):
            chi2 = sum((c.get(d, 0) - W / 10) ** 2 / (W / 10) for d in range(10))
            tot += 1
            sig += chi2_sf(chi2, 9) < 0.05
    return sig, tot


def run(conn):
    rows = conn.execute("SELECT number FROM draws ORDER BY draw_no").fetchall()
    seqs = [[int(str(r[0]).zfill(3)[i]) for r in rows] for i in range(3)]
    n = len(rows)

    results = []  # 持続性・的中率の検定
    for W in WINDOWS:
        trials = hot = cold = 0
        for seq in seqs:
            t, h, c = hot_cold_hits(seq, W)
            trials += t; hot += h; cold += c
        for kind, hits in (("ホット(最多)", hot), ("コールド(最少)", cold)):
            z, p = binom_test(hits, trials, 0.1)
            results.append({"kind": f"{kind}の次回的中率", "W": W, "obs": hits / trials * 100, "exp": 10.0,
                            "detail": f"{hits}/{trials}回", "stat": f"z={z:+.2f}", "p": p})
        r, npairs, zr = persistence(seqs, W)
        results.append({"kind": "偏りの持続(次ブロックとのz相関)", "W": W, "obs": r, "exp": 0.0,
                        "detail": f"{npairs}組", "stat": f"r={r:+.3f}", "p": norm_two_sided_p(zr), "is_r": True})

    m = len(results)
    thr = ALPHA / m
    for t in results:
        t["level"] = 2 if t["p"] < thr else (1 if t["p"] < ALPHA else 0)

    blocks = []
    for W in WINDOWS:
        sig, tot = significant_block_rate(seqs, W)
        blocks.append({"W": W, "sig": sig, "tot": tot, "pct": sig / tot * 100})
    return {"n": n, "results": results, "m": m, "threshold": thr, "blocks": blocks}


def main():
    from db_common import connect
    conn = connect()
    try:
        res = run(conn)
    finally:
        conn.close()
    print(f"抽せん {res['n']}回 / 検定 {res['m']}件 / Bonferroni閾値 p<{res['threshold']:.4f}")
    for t in res["results"]:
        unit = "" if t.get("is_r") else "%"
        print(f"W={t['W']:>3} {t['kind']:<24} 実績 {t['obs']:>7.3f}{unit} 理論 {t['exp']:.1f}{unit} "
              f"{t['stat']:>9} p={t['p']:.4f} {['範囲内','補正前のみ','有意'][t['level']]}  ({t['detail']})")
    print("\n一時的な偏り(p<0.05)が見えたブロックの割合（偶然でも約5%）")
    for b in res["blocks"]:
        print(f"  W={b['W']:>3}: {b['sig']}/{b['tot']} = {b['pct']:.1f}%")


if __name__ == "__main__":
    main()
