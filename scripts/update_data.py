#!/usr/bin/env python3
"""
最新データへの自動更新（スキル起動時に実行する想定）。

主手段: mk-mode.com の NUMBERS3_ALL.csv を再ダウンロードして取り込む
        （ストレート/ボックス/セット/ミニが1ファイルで揃うため）。
フォールバック: 主手段が失敗した場合、numbers-renban.tokyo から差分のみスクレイピング
        （ストレートのみ。box/set/miniはNULLのままになる）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect, get_max_draw_no
import import_csv
import scrape_update

ROOT = Path(__file__).resolve().parent.parent
CSV_URL = "https://www.mk-mode.com/rails/loto/NUMBERS3_ALL.csv"
CSV_PATH = ROOT / "data" / "numbers3_mkmode_all.csv"
UA = "Mozilla/5.0 (compatible; numbers3-db-collector/1.0; personal use)"


def update_via_csv(conn) -> int:
    resp = requests.get(CSV_URL, headers={"User-Agent": UA}, timeout=20)
    resp.raise_for_status()
    CSV_PATH.write_bytes(resp.content)
    rows = import_csv.parse_csv(CSV_PATH)
    return import_csv.upsert_draws(conn, rows)


def update_via_scrape(conn) -> int:
    max_draw_no = get_max_draw_no(conn)
    rows = scrape_update.scrape_list(stop_at_draw_no=max_draw_no, full=False)
    if not rows:
        return 0
    return scrape_update.upsert_draws(conn, rows)


def main():
    conn = connect()
    try:
        before = get_max_draw_no(conn)
        try:
            n = update_via_csv(conn)
            print(f"[mk-mode CSV] 更新処理件数: {n}")
        except Exception as e:
            print(f"[mk-mode CSV] 取得失敗（{e}） → numbers-renban.tokyoへフォールバック")
            n = update_via_scrape(conn)
            print(f"[renban差分スクレイプ] 新規取得件数: {n}（box/set/miniは未取得のままです）")

        after = get_max_draw_no(conn)
        if after > before:
            print(f"最新回号: 第{before}回 → 第{after}回 に更新されました")
        else:
            print(f"最新回号: 第{after}回（変化なし、既に最新）")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
