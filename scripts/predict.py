#!/usr/bin/env python3
"""
ナンバーズ3 当選予想候補の抽出（平均間隔フィルタ）。

考え方:
  1. 番号ごとに「同じ番号が当せんする平均間隔（回数）」を算出する
  2. 番号ごとに「最後にその番号が当せんした回号」を取得する
  3. 最終当せん回から現在までの経過回数が、平均間隔にまだ達していない番号は
     「まだ出にくい時期」として予想候補から除外する
     （経過回数 >= 平均間隔 の番号だけが候補として残る）

注意: 各抽せんは独立試行であり、この経過回数は次回の当せん確率を変えるものではない。
      ここでの「候補」は過去の出現パターン（サンプリング変動）に基づく絞り込みであり、
      当せんを保証するものではない。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect, box_key_of
from analyze import format_date_ja

# win_count が1以下（平均間隔の算出に必要な間隔サンプルが0個）の番号は
# 判定不能のため、安全側（除外しない＝候補に残す）として扱う
MIN_COUNT_FOR_INTERVAL = 2


def get_candidates(conn, mode: str, min_count: int = MIN_COUNT_FOR_INTERVAL):
    """平均間隔フィルタを適用し、(candidates, excluded, latest_draw_no) を返す。

    各要素は dict: key, win_count, avg_interval, last_win_draw_no, last_win_date, draws_elapsed
    candidates: draws_elapsed >= avg_interval（まだ平均間隔未達の番号は excluded 側に入る）
    """
    if mode == "straight":
        view, key_col = "v_number_intervals", "number"
    elif mode == "box":
        view, key_col = "v_box_intervals", "box_key"
    elif mode == "digit":
        view, key_col = "v_digit_intervals", "digit"
    else:
        raise ValueError(f"unknown mode: {mode}")

    latest_draw_no = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()[0]

    rows = conn.execute(
        f"""SELECT {key_col}, win_count, last_win_date, last_win_draw_no, avg_interval
            FROM {view}
            WHERE win_count >= ?
            ORDER BY win_count DESC, last_win_draw_no ASC""",
        (min_count,),
    ).fetchall()

    candidates, excluded = [], []
    for key, win_count, last_win_date, last_win_draw_no, avg_interval in rows:
        draws_elapsed = latest_draw_no - last_win_draw_no
        entry = {
            "key": key,
            "win_count": win_count,
            "last_win_date": last_win_date,
            "last_win_draw_no": last_win_draw_no,
            "avg_interval": avg_interval,
            "draws_elapsed": draws_elapsed,
        }
        if avg_interval is not None and draws_elapsed < avg_interval:
            excluded.append(entry)
        else:
            candidates.append(entry)

    return candidates, excluded, latest_draw_no


def _print_entry(rank: int, entry: dict, number_label: str, verb: str):
    print(f"第{rank}位: {number_label}「{entry['key']}」")
    print(
        f"  {verb}回数：{entry['win_count']}回、"
        f"平均{verb}間隔：{entry['avg_interval']:.1f}回、"
        f"最終{verb}：第{entry['last_win_draw_no']}回（{format_date_ja(entry['last_win_date'])}）、"
        f"最終{verb}から{entry['draws_elapsed']}回経過"
    )


def show_predict(conn, mode: str, label: str, number_label: str, top: int, min_count: int,
                  verb: str = "当選"):
    candidates, excluded, latest_draw_no = get_candidates(conn, mode, min_count)

    print(f"\n=== {label} 予想候補（平均間隔フィルタ・第{latest_draw_no}回時点） ===")
    print(f"候補 {len(candidates)}件 / 除外（平均間隔未達） {len(excluded)}件 "
          f"（判定対象：{verb}回数>={min_count}）")

    print(f"\n--- 候補（{verb}回数が多い順・上位{top}件） ---")
    shown = sorted(candidates, key=lambda e: (-e["win_count"], e["last_win_draw_no"]))[:top]
    for rank, entry in enumerate(shown, start=1):
        _print_entry(rank, entry, number_label, verb)

    print(f"\n--- 除外（まだ平均間隔に達していない・上位{min(top, len(excluded))}件） ---")
    shown_excluded = sorted(excluded, key=lambda e: (-e["win_count"], e["last_win_draw_no"]))[:top]
    for rank, entry in enumerate(shown_excluded, start=1):
        _print_entry(rank, entry, number_label, verb)


def _get_popularity_classification(conn):
    """各数字を「不人気」「普通」「人気」に分類（配当ベース）"""
    from statistics import mean, stdev

    # 各数字の平均配当を計算
    results = conn.execute(
        "SELECT number, straight_amount FROM draws ORDER BY draw_no"
    ).fetchall()

    number_payouts = {}
    for number, amount in results:
        if number not in number_payouts:
            number_payouts[number] = []
        number_payouts[number].append(amount)

    # 全体の平均と標準偏差
    all_payouts = [a for p in number_payouts.values() for a in p]
    overall_avg = mean(all_payouts)
    overall_stdev = stdev(all_payouts)

    # 閾値
    high_threshold = overall_avg + overall_stdev * 0.5
    low_threshold = overall_avg - overall_stdev * 0.5

    # 分類
    classification = {}
    for number, payouts in number_payouts.items():
        avg = mean(payouts)
        if avg >= high_threshold:
            classification[number] = "不人気"
        elif avg <= low_threshold:
            classification[number] = "人気"
        else:
            classification[number] = "普通"

    return classification


def _get_high_payout_numbers(conn):
    """配当が高い数字（不人気）を実データから計算"""
    classification = _get_popularity_classification(conn)
    return {num for num, pop in classification.items() if pop == "不人気"}


# キャッシュ用のグローバル変数
_popularity_cache = {}

def get_number_popularity(conn, number: str) -> str:
    """指定された数字の人気度を返す（「不人気」「普通」「人気」）"""
    global _popularity_cache
    if not _popularity_cache:
        _popularity_cache = _get_popularity_classification(conn)
    return _popularity_cache.get(number, "普通")


def get_pickup_candidates_high_yield(conn, min_count: int = MIN_COUNT_FOR_INTERVAL, top: int = 10):
    """ストレート傾向で配当が高い数字（不人気）のみを候補に"""
    straight_candidates, _straight_excluded, _ = get_candidates(conn, "straight", min_count)
    digit_candidates, _digit_excluded, _ = get_candidates(conn, "digit", min_count)
    digit_candidate_set = {int(e["key"]) for e in digit_candidates}

    # 配当が高い数字（不人気）を取得
    high_payout_numbers = _get_high_payout_numbers(conn)

    # ストレート候補で、かつ配当が高い数字のみを選出
    matched = [
        e for e in straight_candidates
        if e["key"] in high_payout_numbers and all(int(ch) in digit_candidate_set for ch in e["key"])
    ]
    matched.sort(key=lambda e: (-e["win_count"], e["last_win_draw_no"]))

    return matched[:top], digit_candidate_set


def get_pickup_candidates(conn, min_count: int = MIN_COUNT_FOR_INTERVAL, top: int = 10):
    """「ストレート当選傾向」の候補（平均間隔以上経過）かつ、その3桁すべてが
    「1桁の出現間隔」でも候補（平均間隔以上経過）である番号を抽出する（両条件のAND）。
    戻り値: (上位top件のリスト, 候補となった1桁の集合)
    """
    straight_candidates, _straight_excluded, _ = get_candidates(conn, "straight", min_count)
    digit_candidates, _digit_excluded, _ = get_candidates(conn, "digit", min_count)
    digit_candidate_set = {int(e["key"]) for e in digit_candidates}

    matched = [
        e for e in straight_candidates
        if all(int(ch) in digit_candidate_set for ch in e["key"])
    ]
    matched.sort(key=lambda e: (-e["win_count"], e["last_win_draw_no"]))
    return matched[:top], digit_candidate_set




def save_pickup(conn, matched: list[dict], based_on_draw_no: int) -> None:
    """ピックアップ結果をpickupsテーブルに保存する（同じbased_on_draw_noは上書き）。
    同一データからの再実行は同じ結果になるため、上書きしても履歴は破壊されない。
    """
    conn.execute("DELETE FROM pickups WHERE based_on_draw_no = ?", (based_on_draw_no,))
    conn.executemany(
        """INSERT INTO pickups
               (based_on_draw_no, rank, number, box_key, win_count, avg_interval, draws_elapsed)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (based_on_draw_no, rank, e["key"], box_key_of(e["key"]),
             e["win_count"], e["avg_interval"], e["draws_elapsed"])
            for rank, e in enumerate(matched, start=1)
        ],
    )
    conn.commit()


def show_pickup(conn, top: int, min_count: int):
    matched, digit_candidate_set = get_pickup_candidates(conn, min_count, top)
    digit_label = "".join(str(d) for d in sorted(digit_candidate_set))
    latest_draw_no = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()[0]
    save_pickup(conn, matched, latest_draw_no)

    print(f"\n=== 今日のピックアップ数字（ストレート候補 × 1桁候補の両条件・上位{top}件） ===")
    print(f"第{latest_draw_no}回時点のデータに基づく予想（対象：第{latest_draw_no + 1}回）。pickupsテーブルに保存済み")
    print(f"1桁候補（平均間隔以上経過）: {digit_label}")
    for rank, entry in enumerate(matched, start=1):
        _print_entry(rank, entry, "当選数字", "当選")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=10, help="表示件数（デフォルト10）")
    parser.add_argument("--min-count", type=int, default=MIN_COUNT_FOR_INTERVAL,
                         help="この回数以上出現した番号のみ判定対象（デフォルト2、平均間隔算出に最低限必要）")
    parser.add_argument("--mode", choices=["straight", "box", "digit", "pickup", "both"], default="straight")
    args = parser.parse_args()

    conn = connect()
    try:
        if args.mode in ("straight", "both"):
            show_predict(conn, "straight", "ストレート（並び順まで一致）", "当選数字",
                         args.top, args.min_count)
        if args.mode in ("box", "both"):
            show_predict(conn, "box", "ボックス（桁の組合せ一致）", "ボックス数字",
                         args.top, args.min_count)
        if args.mode == "digit":
            show_predict(conn, "digit", "1桁（0〜9・位置を問わず出現）", "数字",
                         args.top, args.min_count, verb="出現")
        if args.mode == "pickup":
            show_pickup(conn, args.top, args.min_count)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
