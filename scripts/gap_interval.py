#!/usr/bin/env python3
"""
ナンバーズ3 当せん間隔の分布と「今強い／弱い間隔」、およびその有効性のウォークフォワード検証。

  間隔 = 同じストレート番号が再び当せんするまでの回数。
  1. 全期間の間隔分布を、理論分布（窓が有限であることを補正した幾何分布）と比較（χ²検定）
  2. 直近W回に終わった間隔の分布から、理論より多い区間（強い）／少ない区間（弱い）を求める
  3. 経過回数がその区間に入っている番号を候補として列挙
  4. 過去で選び未来で測る検証: 「強い／弱い区間の近くの番号」「経過回数が多い／少ない順」が、
     次回の当せんをどれだけ含むかを理論値（Σ 候補数/1000）と比べる。選び方は過去のみに依存するため
     各回の的中は厳密にベルヌーイ試行で、z検定が成り立つ。
注意: 同じ番号の再当せんは前回からの経過回数に依存しない（無記憶）ので、強弱は次回を予測しない。
"""
from __future__ import annotations

import math
import sys
from collections import deque
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from theory_vs_actual import chi2_sf, ALPHA

P = 0.001
B = 250            # 区間の幅（回）
NB = 12            # 区間数（最後は2751回以上）
T0 = 1500          # 検証の開始時点（それまでは間隔が溜まるのを待つ）
WINDOWS = (1000, 2000)
CURRENT_W = 1000   # 「現在の強弱」に使う窓
MIN_EXP = 3.0      # 期待度数がこれ未満の区間は強弱の判定対象外


def labels():
    return [f"{i * B + 1}〜{(i + 1) * B}" for i in range(NB - 1)] + [f"{(NB - 1) * B + 1}〜"]


def bin_of(g):
    return int(min((g - 1) // B, NB - 1))


def expected_gaps(n_end: int, window: int | None = None):
    """終端位置が窓内にある、完了した間隔の期待数（1000番号分）。window=None なら全期間（0..n_end-1）。
    窓の左端 s0..n_end-1 に終わる間隔gは、始点 e-g >= 0 を満たす e のみ数えられる。"""
    lo = 0 if window is None else max(0, n_end - window)
    e = np.zeros(NB)
    for g in range(1, n_end):
        first = max(lo, g)           # 終端 e の最小値（始点が0以上）
        cnt = n_end - first
        if cnt > 0:
            e[bin_of(g)] += 1000 * cnt * P * P * (1 - P) ** (g - 1)
    return e


def norm_p(z):
    return math.erfc(abs(z) / math.sqrt(2))


def run(conn):
    nums = np.array([int(r[0]) for r in conn.execute("SELECT number FROM draws ORDER BY draw_no")])
    draw_nos = [r[0] for r in conn.execute("SELECT draw_no FROM draws ORDER BY draw_no")]
    n = len(nums)

    # --- 1. 全期間の分布 ---
    last = {}
    obs = np.zeros(NB)
    for t, x in enumerate(nums):
        if x in last:
            obs[bin_of(t - last[x])] += 1
        last[x] = t
    exp = expected_gaps(n)
    chi2 = float(((obs - exp) ** 2 / exp).sum())
    dist = {"labels": labels(), "obs": obs.tolist(), "exp": exp.tolist(), "chi2": chi2, "df": NB - 1,
            "p": chi2_sf(chi2, NB - 1), "total": int(obs.sum())}

    # --- 2〜4. ウォークフォワード＋現在の強弱 ---
    strategies = [("strong", w) for w in WINDOWS] + [("weak", w) for w in WINDOWS] + [("overdue", 0), ("recent", 0)]
    acc = {s: {"trials": 0, "hits": 0, "sump": 0.0, "sumv": 0.0} for s in strategies}
    expcache = {}
    state = {w: {"recent": deque(), "cnt": np.zeros(NB)} for w in WINDOWS}
    last_arr = np.full(1000, -10 ** 9)
    seen = np.zeros(1000, bool)
    current = None

    def pick(mode, w, t, el):
        """時点t（draw t まで既知）での候補マスクと、強弱判定に使った区間を返す。"""
        if mode in ("strong", "weak"):
            cnt = state[w]["cnt"]
            tot = cnt.sum()
            if tot < 50:
                return None, None, None
            key = ((t + 1) // 50, w)
            if key not in expcache:
                expcache[key] = expected_gaps(t + 1, w)
            ex = expcache[key]
            e_b = np.maximum(ex * tot / ex.sum(), 1e-9)
            z = (cnt - e_b) / np.sqrt(e_b)
            z[e_b < MIN_EXP] = 0.0
            b = int(np.argmax(z)) if mode == "strong" else int(np.argmin(z))
            gb = el + 1
            mask = seen & (np.minimum((gb - 1) // B, NB - 1) == b)
            return mask, b, z
        mask = np.zeros(1000, bool)
        if mode == "overdue":
            mask[np.argsort(-np.where(seen, el, -1))[:100]] = True
        else:
            mask[np.argsort(np.where(seen, el, 10 ** 9))[:100]] = True
        return mask, None, None

    for t in range(n):
        x = nums[t]
        if seen[x]:
            g = t - last_arr[x]
            for w in WINDOWS:
                state[w]["recent"].append((t, g))
                state[w]["cnt"][bin_of(g)] += 1
        seen[x] = True
        last_arr[x] = t
        for w in WINDOWS:
            rq, cnt = state[w]["recent"], state[w]["cnt"]
            while rq and rq[0][0] <= t - w:
                cnt[bin_of(rq.popleft()[1])] -= 1
        el = t - last_arr
        if t == n - 1:
            mask, b, z = pick("strong", CURRENT_W, t, el)
            mask_w, bw, _ = pick("weak", CURRENT_W, t, el)
            current = {"W": CURRENT_W, "strong_bin": b, "weak_bin": bw, "z": z.tolist(), "el": el.copy()}
            current["strong_mask"], current["weak_mask"] = mask, mask_w
            break
        if t < T0:
            continue
        for mode, w in strategies:
            mask, _, _ = pick(mode, w, t, el)
            if mask is None or not mask.any():
                continue
            k = int(mask.sum())
            pt = k / 1000
            a = acc[(mode, w)]
            a["trials"] += 1
            a["hits"] += int(mask[nums[t + 1]])
            a["sump"] += pt
            a["sumv"] += pt * (1 - pt)

    names = {"strong": "強い間隔の近くの番号", "weak": "弱い間隔の近くの番号",
             "overdue": "経過回数が多い順（上位100）", "recent": "経過回数が少ない順（上位100）"}
    tests = []
    for (mode, w), a in acc.items():
        z = (a["hits"] - a["sump"]) / math.sqrt(a["sumv"])
        tests.append({"name": names[mode], "W": w, "trials": a["trials"], "hits": a["hits"], "exp": a["sump"],
                      "ratio": a["hits"] / a["sump"], "z": z, "p": norm_p(z)})
    thr = ALPHA / len(tests)
    for tst in tests:
        tst["level"] = 2 if tst["p"] < thr else (1 if tst["p"] < ALPHA else 0)

    # 現在の候補
    def cands(mask):
        idx = [int(i) for i in np.where(mask)[0]]
        idx.sort(key=lambda i: -current["el"][i])
        return [(f"{i:03d}", int(current["el"][i])) for i in idx]
    cur = {
        "W": CURRENT_W, "latest_draw_no": draw_nos[-1],
        "strong": {"label": labels()[current["strong_bin"]], "z": current["z"][current["strong_bin"]],
                   "cands": cands(current["strong_mask"])},
        "weak": {"label": labels()[current["weak_bin"]], "z": current["z"][current["weak_bin"]],
                 "cands": cands(current["weak_mask"])},
        "zs": current["z"],
    }
    return {"n": n, "dist": dist, "tests": tests, "threshold": thr, "current": cur}


def main():
    from db_common import connect
    conn = connect()
    try:
        r = run(conn)
    finally:
        conn.close()
    d = r["dist"]
    print(f"全期間の間隔分布 {d['total']}件: chi2={d['chi2']:.2f} df={d['df']} p={d['p']:.3f}")
    for l, o, e in zip(d["labels"], d["obs"], d["exp"]):
        print(f"  {l:>10}: 実績 {int(o):>5} 理論 {e:7.1f}")
    print(f"\n検証 {len(r['tests'])}件 / p<{r['threshold']:.4f}")
    for t in r["tests"]:
        print(f"  {t['name']:<20} W={t['W']:<5} 的中{t['hits']} 理論{t['exp']:.1f} 比{t['ratio']:.3f} z={t['z']:+.2f} p={t['p']:.3f}")
    c = r["current"]
    print(f"\n現在(第{c['latest_draw_no']}回時点, 窓{c['W']}回): 強い区間 {c['strong']['label']}(z={c['strong']['z']:+.2f}) 候補{len(c['strong']['cands'])}個 / "
          f"弱い区間 {c['weak']['label']}(z={c['weak']['z']:+.2f}) 候補{len(c['weak']['cands'])}個")


if __name__ == "__main__":
    main()
