#!/usr/bin/env python3
"""
ナンバーズ3 商品別（ストレート・ボックス・ミニ）人気度と期待値の検定。

商品ごとの構造:
  ストレート: 当せん確率 1/1000。
  ボックス  : 当せん確率は並び替えの数/1000（シングル型6通り=0.6%、ダブル型3通り=0.3%）。
              当せん金の水準が型で違うので、型ごとに規格化する。ぞろ目は対象外。
  ミニ      : 下2桁のみ。当せん確率 1/100。

方法（popularity_ev.py と同じ考え方）:
  当せん番号は一様ランダム → 当たった回の当せん金は、その番号の人気（買う人の偏り）を偏りなく標本化する。
  各回の当せん金を型ごとの前後中央値で割った「相対配当」を、特徴別に Welch z検定する。

前向き検証:
  前半60%の回で「不人気（=当たれば高配当）な番号」を予測し、後半40%で
  『選んだ番号を毎回すべて買い続けた場合の実際の還元率』を直接計算する（仮定なし）。
  比較対象は「全番号を毎回買う場合」で、同じ回の差を対にして z検定する。
"""
from __future__ import annotations

import math
import sys
from itertools import permutations
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from theory_vs_actual import ALPHA
from popularity_ev import WIN, PRICE, MIN_N, DAYS, median, norm_p, welch, is_birthday

TRAIN_FRAC = 0.6
SELECT_FRACS = (0.1, 0.2, 0.5)


# ---------- 商品定義 ----------
def box_key(num): return "".join(sorted(num))
def box_group(key): return "ダブル型" if len(set(key)) == 2 else "シングル型"
def box_perms(key): return len(set(permutations(key)))


def all_keys(product):
    if product == "straight":
        return [f"{i:03d}" for i in range(1000)]
    if product == "mini":
        return [f"{i:02d}" for i in range(100)]
    ks = set()
    for i in range(1000):
        k = box_key(f"{i:03d}")
        if len(set(k)) > 1:
            ks.add(k)
    return sorted(ks)


def win_prob(product, key):
    if product == "straight": return 1 / 1000
    if product == "mini": return 1 / 100
    return box_perms(key) / 1000


def _is_run(key):  # 連番（昇順に1ずつ）。ストレートは降順も含める
    d = [int(c) for c in key]
    return all(b - a == 1 for a, b in zip(d, d[1:]))


def _is_run_any(key):
    d = [int(c) for c in key]
    return all(b - a == 1 for a, b in zip(d, d[1:])) or all(a - b == 1 for a, b in zip(d, d[1:]))


def _box_birthday(key):  # 並べ替えて月日として実在する並びがある
    return any(is_birthday("".join(p)) for p in set(permutations(key)))


def _mini_day(key): return 1 <= int(key) <= 31


def _digit_feats():
    return [(f"「{d}」を含む", (lambda k, d=d: str(d) in k)) for d in range(10)]


FEATURES = {
    "straight": [
        ("ぞろ目", lambda k: len(set(k)) == 1),
        ("連番(昇順・降順)", _is_run_any),
        ("誕生日型(月日として実在)", is_birthday),
        ("下2桁が31以下", lambda k: 1 <= int(k[1:]) <= 31),
        ("合計値が大きい(18〜27)", lambda k: sum(map(int, k)) >= 18),
    ] + _digit_feats(),
    "box": [
        ("連番(012〜789)", _is_run),
        ("並べ替えると誕生日型", _box_birthday),
        ("合計値が大きい(18〜27)", lambda k: sum(map(int, k)) >= 18),
        ("合計値が小さい(0〜9)", lambda k: sum(map(int, k)) <= 9),
    ] + _digit_feats(),
    "mini": [
        ("ぞろ目(00・11…)", lambda k: k[0] == k[1]),
        ("連番(12・21など)", _is_run_any),
        ("日付型(01〜31)", _mini_day),
    ] + _digit_feats(),
}

LABEL = {"straight": "ストレート", "box": "ボックス", "mini": "ミニ"}


def load(conn, product):
    """戻り値: [(draw_no, key, amount, group)]（当せん金が正の回のみ）"""
    if product == "straight":
        rows = conn.execute("SELECT draw_no, number, straight_amount FROM draws WHERE straight_amount>0 ORDER BY draw_no").fetchall()
        return [(a, b, c, "all") for a, b, c in rows]
    if product == "mini":
        rows = conn.execute("SELECT draw_no, number, mini_amount FROM draws WHERE mini_amount>0 ORDER BY draw_no").fetchall()
        return [(a, b[1:], c, "all") for a, b, c in rows]
    rows = conn.execute("SELECT draw_no, number, box_amount FROM draws WHERE box_amount>0 ORDER BY draw_no").fetchall()
    out = []
    for a, b, c in rows:
        k = box_key(b)
        if len(set(k)) > 1:
            out.append((a, k, c, box_group(k)))
    return out


def with_relative(rows):
    """グループごとの前後中央値で割り、グループ内の平均が1.00になるよう規格化。戻り値: [(no,key,amount,group,rel)]"""
    by = {}
    for i, r in enumerate(rows):
        by.setdefault(r[3], []).append(i)
    rel = [0.0] * len(rows)
    for g, idxs in by.items():
        amts = [rows[i][2] for i in idxs]
        r = []
        for j in range(len(idxs)):
            lo, hi = max(0, j - WIN), min(len(idxs), j + WIN + 1)
            r.append(amts[j] / median(amts[lo:hi]))
        sc = sum(r) / len(r)
        for j, i in enumerate(idxs):
            rel[i] = r[j] / sc
    return [(*rows[i], rel[i]) for i in range(len(rows))]


def design(product, key):
    if product == "straight":
        v = [0.0] * 31
        for p in range(3):
            v[p * 10 + int(key[p])] = 1
        v[30] = float(is_birthday(key))
        return v
    if product == "mini":
        v = [0.0] * 21
        for p in range(2):
            v[p * 10 + int(key[p])] = 1
        v[20] = float(_mini_day(key))
        return v
    v = [0.0] * 11
    for c in key:
        v[int(c)] += 1
    v[10] = float(len(set(key)) == 2)
    return v


def fit_predict(product, train):
    X = np.array([design(product, r[1]) for r in train])
    y = np.log([r[4] for r in train])
    X1 = np.hstack([X, np.ones((len(X), 1))])
    lam = 1.0
    A = X1.T @ X1 + lam * np.eye(X1.shape[1])
    A[-1, -1] -= lam  # 切片は正則化しない
    beta = np.linalg.solve(A, X1.T @ y)
    return lambda key: float(np.append(design(product, key), 1.0) @ beta)


def forward_test(product, data):
    cut = int(len(data) * TRAIN_FRAC)
    train, test = data[:cut], data[cut:]
    predict = fit_predict(product, train)
    keys = all_keys(product)
    # 群ごとの平均当せん金（学習側）で、予想期待値 = 当せん確率 × 平均当せん金 × exp(予測log相対配当)
    gmean = {}
    for g in {r[3] for r in train}:
        a = [r[2] for r in train if r[3] == g]
        gmean[g] = sum(a) / len(a)
    def group_of(k):
        return box_group(k) if product == "box" else "all"
    ev = {k: win_prob(product, k) * gmean[group_of(k)] * math.exp(predict(k)) for k in keys}
    order = sorted(keys, key=lambda k: -ev[k])
    nt = len(test)
    amt_by_key = {}
    for i, r in enumerate(test):
        amt_by_key.setdefault(r[1], []).append((i, r[2]))
    def per_draw_return(sel):
        x = np.zeros(nt)
        for k in sel:
            for i, a in amt_by_key.get(k, []):
                x[i] += a
        return x / (len(sel) * PRICE)  # 1口あたりの還元（回ごと）
    base = per_draw_return(keys)
    rows = []
    for f in SELECT_FRACS:
        k = max(1, round(len(keys) * f))
        sel = order[:k]
        x = per_draw_return(sel)
        d = x - base
        z = d.mean() / (d.std(ddof=1) / math.sqrt(nt))
        rows.append({"frac": f, "k": k, "ret": x.mean() * 100, "se": x.std(ddof=1) / math.sqrt(nt) * 100,
                     "base": base.mean() * 100, "diff": d.mean() * 100, "z": z, "p": norm_p(z)})
    # 逆（人気と予測した番号）
    k = max(1, round(len(keys) * SELECT_FRACS[0]))
    pop = per_draw_return(order[-k:]).mean() * 100
    return {"rows": rows, "train_n": cut, "test_n": nt, "popular_ret": pop, "base": base.mean() * 100,
            "top": order[:5], "bottom": order[-5:][::-1], "nkeys": len(keys)}


def class_return(product, data, fn, overall_by_group):
    """特徴の番号（全種類）を毎回買った場合の推定還元率（%）。型ごとの 当せん確率×平均当せん金×平均相対配当 で積み上げる。"""
    keys = [k for k in all_keys(product) if fn(k)]
    if not keys:
        return None
    gs = {}
    for k in keys:
        g = box_group(k) if product == "box" else "all"
        gs.setdefault(g, []).append(k)
    total = 0.0
    for g, ks in gs.items():
        rels = [r[4] for r in data if r[3] == g and fn(r[1])]
        if not rels:
            return None
        m = sum(rels) / len(rels)
        total += sum(win_prob(product, k) for k in ks) * overall_by_group[g] * m
    return total / len(keys) / PRICE * 100


def features(product, data):
    n = len(data)
    mean_amt = {}
    for g in {r[3] for r in data}:
        a = [r[2] for r in data if r[3] == g]
        mean_amt[g] = sum(a) / len(a)
    allk = all_keys(product)
    out = []
    for name, fn in FEATURES[product]:
        yes = [r[4] for r in data if fn(r[1])]
        no = [r[4] for r in data if not fn(r[1])]
        if len(yes) < MIN_N or len(no) < MIN_N:
            continue
        z, se = welch(yes, no)
        share = sum(1 for k in allk if fn(k)) / len(allk) * 100
        out.append({"name": name, "n": len(yes), "share": share, "mean": sum(yes) / len(yes), "se": se, "z": z,
                    "p": norm_p(z), "ret": class_return(product, data, fn, mean_amt)})
    thr = ALPHA / len(out)
    for f in out:
        f["level"] = 2 if f["p"] < thr else (1 if f["p"] < ALPHA else 0)
    return out, thr


def split_corr(data):
    half = len(data) // 2
    def per(sub):
        acc = {}
        for r in sub:
            acc.setdefault(r[1], []).append(math.log(r[4]))
        return {k: sum(v) / len(v) for k, v in acc.items()}
    a, b = per(data[:half]), per(data[half:])
    ks = sorted(set(a) & set(b))
    xs, ys = np.array([a[k] for k in ks]), np.array([b[k] for k in ks])
    r = float(np.corrcoef(xs, ys)[0, 1])
    return {"r": r, "k": len(ks), "p": norm_p(r * math.sqrt(len(ks) - 2))}


def run(conn):
    res = {"products": []}
    for product in ("straight", "box", "mini"):
        data = with_relative(load(conn, product))
        feats, thr = features(product, data)
        res["products"].append({
            "key": product, "label": LABEL[product], "n": len(data), "features": feats, "threshold": thr,
            "forward": forward_test(product, data), "split": split_corr(data),
        })
    return res


def main():
    from db_common import connect
    conn = connect()
    try:
        res = run(conn)
    finally:
        conn.close()
    for p in res["products"]:
        print(f"\n===== {p['label']}（{p['n']}回 / 検定{len(p['features'])}件 / p<{p['threshold']:.4f}）=====")
        print(f"{'特徴':<24}{'該当率':>7}{'n':>6}{'相対配当':>9}{'±SE':>7}{'z':>8}{'p':>8}  推定還元率  判定")
        for f in sorted(p["features"], key=lambda x: x["p"]):
            ret = "  n/a" if f["ret"] is None else f"{f['ret']:5.1f}%"
            print(f"{f['name']:<22}{f['share']:>6.1f}%{f['n']:>6}{f['mean']:>9.3f}{f['se']:>7.3f}{f['z']:>+8.2f}{f['p']:>8.4f}  {ret:>8}  {['範囲内','補正前のみ','有意'][f['level']]}")
        s = p["split"]
        print(f"個別番号の人気 前半/後半相関 r={s['r']:+.3f} ({s['k']}個) p={s['p']:.4f}")
        fw = p["forward"]
        print(f"[前向き検証] 前半{fw['train_n']}回で学習→後半{fw['test_n']}回: 全番号を買う場合の還元率 {fw['base']:.1f}%")
        for r in fw["rows"]:
            print(f"  不人気上位{r['frac']*100:.0f}%({r['k']}/{fw['nkeys']}個): 還元率 {r['ret']:.1f}±{r['se']:.1f}% 差{r['diff']:+.1f}pt z={r['z']:+.2f} p={r['p']:.4f}")
        print(f"  参考 人気と予測した10%: 還元率 {fw['popular_ret']:.1f}%   予測 最不人気{fw['top']} 最人気{fw['bottom']}")


if __name__ == "__main__":
    main()
