#!/usr/bin/env python3
"""
ナンバーズ3 人気度（買う人の偏り）と期待値の検定。

考え方:
  当せん番号は一様ランダムなので、「その番号が当たった回の当せん金」は、買う人がその番号を
  どれだけ選んでいたか（人気）を偏りなしにサンプリングしたものになる。
  当せん金 ≈ 売上÷当せん口数 なので、人気が高い番号ほど当せん金は低い。
  ストレート1口の期待値 = (1/1000) × 当せん金 ÷ 200円 なので、相対配当は期待値の倍率そのもの。

手順:
  1. 各回の当せん金を、前後±WIN回の中央値で割って時期ごとの売上変動を除く（相対配当）
  2. 全体平均が1.00になるよう規格化
  3. 番号の特徴ごとに「該当」vs「非該当」の平均相対配当を Welch z検定（Bonferroni補正）
  4. 個別番号の人気が時間を超えて安定か（前半/後半の相関）で、特徴に依らない構造の有無も確認
注意: 当せん金は参加者の行動で決まる量で、「当たる確率」はどの番号も 1/1000 のまま。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from theory_vs_actual import ALPHA

WIN = 100          # 相対配当を求める前後の回数
PRICE = 200        # 1口の価格（円）
MIN_N = 30         # 検定に使う最小標本数
DAYS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def norm_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def median(xs):
    s = sorted(xs)
    k = len(s)
    return s[k // 2] if k % 2 else (s[k // 2 - 1] + s[k // 2]) / 2


# ---------- 番号の特徴（名前, 判定関数, 説明） ----------
def _d(num):
    return [int(c) for c in num]


def is_zorome(n): d = _d(n); return d[0] == d[1] == d[2]
def is_renban(n): d = _d(n); return (d[1] - d[0], d[2] - d[1]) in ((1, 1), (-1, -1))
def is_double(n): return len(set(n)) == 2
def is_single(n): return len(set(n)) == 3
def is_birthday(n):  # 百の位=月(1〜9)、下2桁=日として実在する日付
    m, dd = int(n[0]), int(n[1:])
    return 1 <= m <= 9 and 1 <= dd <= DAYS[m - 1]
def is_day_le31(n): return 1 <= int(n[1:]) <= 31
def is_777(n): return n == "777"


FEATURES = [
    ("ぞろ目(111〜999,000)", is_zorome, "全桁が同じ数字"),
    ("連番(123・321など)", is_renban, "昇順または降順に1ずつ並ぶ"),
    ("ダブル(同じ数字2つ)", is_double, "例: 112, 505"),
    ("シングル(全て異なる)", is_single, "例: 123, 509"),
    ("誕生日型(月日として実在)", is_birthday, "百の位=月、下2桁=日。例: 131, 925"),
    ("下2桁が31以下", is_day_le31, "日付として読める下2桁"),
    ("「7」を含む", lambda n: "7" in n, "ラッキーセブン"),
    ("「8」を含む", lambda n: "8" in n, "末広がり"),
    ("「4」を含む", lambda n: "4" in n, "忌み数字"),
    ("「9」を含む", lambda n: "9" in n, "忌み数字"),
    ("「0」を含む", lambda n: "0" in n, ""),
    ("「1」を含む", lambda n: "1" in n, ""),
    ("「2」を含む", lambda n: "2" in n, ""),
    ("「3」を含む", lambda n: "3" in n, ""),
    ("「5」を含む", lambda n: "5" in n, ""),
    ("「6」を含む", lambda n: "6" in n, ""),
    ("合計値が小さい(0〜9)", lambda n: sum(_d(n)) <= 9, ""),
    ("合計値が大きい(18〜27)", lambda n: sum(_d(n)) >= 18, ""),
]


def welch(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((x - ma) ** 2 for x in a) / (len(a) - 1)
    vb = sum((x - mb) ** 2 for x in b) / (len(b) - 1)
    se = math.sqrt(va / len(a) + vb / len(b))
    return (ma - mb) / se, se


def load_relative(conn):
    rows = conn.execute(
        "SELECT draw_no, number, straight_amount FROM draws "
        "WHERE straight_amount > 0 ORDER BY draw_no"
    ).fetchall()
    amts = [r[2] for r in rows]
    n = len(rows)
    rel = []
    for i in range(n):
        lo, hi = max(0, i - WIN), min(n, i + WIN + 1)
        rel.append(amts[i] / median(amts[lo:hi]))
    scale = sum(rel) / n
    rel = [x / scale for x in rel]
    data = [(rows[i][0], rows[i][1], rows[i][2], rel[i]) for i in range(n)]
    return data


def fit_additive(train):
    """log相対配当 ≈ 定数 + 桁位置別の数字効果 + 誕生日型効果（バックフィッティング）。"""
    ys = [math.log(r) for _, _, _, r in train]
    nums = [t[1] for t in train]
    mu = sum(ys) / len(ys)
    eff = {(p, d): 0.0 for p in range(3) for d in range(10)}
    bday = 0.0
    bd = [is_birthday(x) for x in nums]
    for _ in range(30):
        for p in range(3):
            for d in range(10):
                idx = [i for i, x in enumerate(nums) if int(x[p]) == d]
                if not idx:
                    continue
                res = [ys[i] - mu - bday * bd[i] - sum(eff[(q, int(nums[i][q]))] for q in range(3) if q != p) for i in idx]
                eff[(p, d)] = sum(res) / len(res)
        idx = [i for i in range(len(nums)) if bd[i]]
        res = [ys[i] - mu - sum(eff[(q, int(nums[i][q]))] for q in range(3)) for i in idx]
        bday = sum(res) / len(res)
    def predict(num):
        return mu + bday * is_birthday(num) + sum(eff[(q, int(num[q]))] for q in range(3))
    return predict


def out_of_sample(data, overall_return, train_frac=0.6, ks=(50, 100, 200, 500)):
    """過去(前半)だけで「当たったときの配当が高そうな番号」を選び、後半で実際の相対配当を測る。"""
    cut = int(len(data) * train_frac)
    train, test = data[:cut], data[cut:]
    predict = fit_additive(train)
    score = {f"{i:03d}": predict(f"{i:03d}") for i in range(1000)}
    order = sorted(score, key=lambda k: -score[k])
    out = []
    for k in ks:
        sel = set(order[:k])
        vals = [t[3] for t in test if t[1] in sel]
        rest = [t[3] for t in test if t[1] not in sel]
        z, se = welch(vals, rest)
        m = sum(vals) / len(vals)
        out.append({"k": k, "n": len(vals), "mean": m, "se": se, "z": z, "p": norm_p(z), "ret": overall_return * m})
    # 逆（人気数字を選んだ場合）
    sel = set(order[-100:])
    vals = [t[3] for t in test if t[1] in sel]
    return {"rows": out, "train_n": len(train), "test_n": len(test), "popular_ret": overall_return * sum(vals) / len(vals),
            "top": order[:5], "bottom": order[-5:][::-1]}


def run(conn):
    data = load_relative(conn)
    n = len(data)
    all_rel = [d[3] for d in data]
    overall_return = sum(d[2] for d in data) / n / PRICE / 1000 * 100  # 全体の還元率(%)

    feats = []
    for name, fn, note in FEATURES:
        yes = [d[3] for d in data if fn(d[1])]
        no = [d[3] for d in data if not fn(d[1])]
        if len(yes) < MIN_N:
            continue
        z, se = welch(yes, no)
        mean_yes = sum(yes) / len(yes)
        theo = sum(1 for i in range(1000) if fn(f"{i:03d}"))  # 000〜999 中の該当数
        feats.append({
            "name": name, "note": note, "n": len(yes), "share": theo / 10,
            "mean": mean_yes, "se": se, "z": z, "p": norm_p(z),
            "ret": overall_return * mean_yes,
        })
    m = len(feats)
    thr = ALPHA / m
    for f in feats:
        f["level"] = 2 if f["p"] < thr else (1 if f["p"] < ALPHA else 0)

    # 個別番号の人気の安定性（前半/後半の相関）
    half = n // 2
    def per_number(sub):
        acc = {}
        for _, num, _, r in sub:
            acc.setdefault(num, []).append(math.log(r))
        return {k: sum(v) / len(v) for k, v in acc.items()}
    a, b = per_number(data[:half]), per_number(data[half:])
    common = sorted(set(a) & set(b))
    xs, ys = [a[k] for k in common], [b[k] for k in common]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    r = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(
        sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    split = {"r": r, "k": len(common), "p": norm_p(r * math.sqrt(len(common) - 2)),
             "n_first": half, "n_second": n - half}

    # 個別番号の相対配当ランキング（参考。標本が少ないため上位/下位は誇張される）
    per = {}
    for _, num, _, rr in data:
        per.setdefault(num, []).append(rr)
    ranked = sorted(((sum(v) / len(v), len(v), k) for k, v in per.items() if len(v) >= 5))
    oos = out_of_sample(data, overall_return)
    return {"oos": oos, "n": n, "overall_return": overall_return, "features": feats, "m": m, "threshold": thr,
            "split": split, "low": ranked[:5], "high": ranked[-5:][::-1], "win": WIN}


def main():
    from db_common import connect
    conn = connect()
    try:
        res = run(conn)
    finally:
        conn.close()
    print(f"対象 {res['n']}回 / 全体還元率 約{res['overall_return']:.1f}% / 検定 {res['m']}件 / Bonferroni p<{res['threshold']:.4f}")
    print(f"{'特徴':<24}{'該当率':>7}{'n':>6}{'相対配当':>9}{'±SE':>7}{'z':>7}{'p':>8}  推定還元率  判定")
    for f in sorted(res["features"], key=lambda x: x["p"]):
        print(f"{f['name']:<22}{f['share']:>6.1f}%{f['n']:>6}{f['mean']:>9.3f}{f['se']:>7.3f}{f['z']:>+7.2f}{f['p']:>8.4f}  {f['ret']:>6.1f}%  {['範囲内','補正前のみ','有意'][f['level']]}")
    s = res["split"]
    print(f"\n個別番号の人気の前半/後半相関: r={s['r']:+.3f} (番号{s['k']}個) p={s['p']:.4f}")
    o = res["oos"]
    print(f"\n[前向き検証] 前半{o['train_n']}回で学習 → 後半{o['test_n']}回で評価（不人気と予測した番号を買った場合）")
    for r in o["rows"]:
        print(f"  上位{r['k']:>3}番号: 後半の相対配当 {r['mean']:.3f}±{r['se']:.3f} (n={r['n']}) z={r['z']:+.2f} p={r['p']:.4f} → 推定還元率 {r['ret']:.1f}%")
    print(f"  参考 人気と予測した100番号: 推定還元率 {o['popular_ret']:.1f}%  / 全体 {res['overall_return']:.1f}%")
    print("  予測 最不人気:", o['top'], " 最人気:", o['bottom'])
    print("相対配当が低い番号(人気):", [(k, round(m, 2), n) for m, n, k in res["low"]])
    print("相対配当が高い番号(不人気):", [(k, round(m, 2), n) for m, n, k in res["high"]])


if __name__ == "__main__":
    main()
