#!/usr/bin/env python3
"""
ナンバーズ3 当選傾向の確認用CLI。

出現回数が多く、かつ最後の当せんから回数が経過している番号を一覧表示する。
注意: 各抽せんは独立試行であり、過去の出現頻度が次回の当せん確率を左右するものではない。
      ここで示すのはあくまで約7000回規模の試行における数字の偏り（サンプリング変動）の把握であり、予測ではない。
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect


def format_date_ja(iso_date: str) -> str:
    y, m, d = iso_date.split("-")
    return f"{int(y)}年{int(m)}月{int(d)}日"


def show_stats(conn, view: str, label: str, number_label: str, top: int, min_count: int, latest_draw_no: int):
    rows = conn.execute(
        f"""SELECT * FROM {view}
            WHERE win_count >= ?
            ORDER BY win_count DESC, last_win_draw_no ASC
            LIMIT ?""",
        (min_count, top),
    ).fetchall()

    print(f"\n=== {label}（上位{len(rows)}件） ===")
    for rank, (key, win_count, last_win_date, last_win_draw_no, _days) in enumerate(rows, start=1):
        draws_elapsed = latest_draw_no - last_win_draw_no
        print(f"第{rank}位: {number_label}「{key}」")
        print(
            f"  内訳：当選回数：{win_count}回、"
            f"最終当選回：第{last_win_draw_no}回（{format_date_ja(last_win_date)}）、"
            f"最終当選回から{draws_elapsed}回経過"
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=10, help="表示件数（デフォルト10）")
    parser.add_argument("--min-count", type=int, default=2, help="この回数以上出現した番号のみ表示")
    parser.add_argument("--mode", choices=["straight", "box", "both"], default="both")
    args = parser.parse_args()

    conn = connect()
    try:
        total, min_date, max_date = conn.execute(
            "SELECT COUNT(*), MIN(draw_date), MAX(draw_date) FROM draws"
        ).fetchone()
        latest_draw_no = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()[0]
        print(f"総抽せん回数: {total}回（第1回〜第{latest_draw_no}回／{min_date} 〜 {max_date}）")

        if args.mode in ("straight", "both"):
            show_stats(conn, "v_number_stats", "ストレート（並び順まで一致）", "当選数字",
                       args.top, args.min_count, latest_draw_no)
        if args.mode in ("box", "both"):
            show_stats(conn, "v_box_stats", "ボックス（桁の組合せ一致）", "ボックス数字",
                       args.top, args.min_count, latest_draw_no)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
