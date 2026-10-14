#!/usr/bin/env python3
"""
numbers-renban.tokyo からナンバーズ3の抽せん結果を取得しDBを更新する。

通常運用: 引数なしで実行 -> 一覧ページを新しい順に取得し、DB未登録の回号のみ追加（ストレートのみ）。
  python3 scrape_update.py

全履歴の新規構築（空DB向け）: 一覧ページを末尾まで全て取得。
  python3 scrape_update.py --full

既存レコードのボックス/セット/ミニ内訳を補完（詳細ページを個別取得・低速）:
  python3 scrape_update.py --enrich [--limit N]

mizuho銀行公式サイトはこの環境からのアクセスがAkamai WAFで403ブロックされたため、
一覧・詳細とも構造が安定しているnumbers-renban.tokyo（robots.txt許可済み）を利用する。
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect, get_max_draw_no, upsert_draws

BASE = "https://numbers-renban.tokyo"
LIST_URL = BASE + "/numbers3/result_all"
DETAIL_URL = BASE + "/numbers3/result/{draw_no}"
UA = "Mozilla/5.0 (compatible; numbers3-db-collector/1.0; personal use)"
REQUEST_INTERVAL_SEC = 1.0


def fetch(url: str, params: dict | None = None) -> str:
    resp = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_list_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.select("table.table-striped tr"):
        link = tr.select_one("a.tdu[href*='/numbers3/result/']")
        if not link:
            continue
        m = re.search(r"第(\d+)回", link.get_text())
        if not m:
            continue
        draw_no = int(m.group(1))

        date_span = tr.select_one("td span.d-none.d-sm-inline")
        date_text = date_span.get_text(strip=True) if date_span else ""
        date_m = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
        if not date_m:
            continue
        draw_date = date_m.group(1)

        num_link = tr.select_one("td.num a.tdu")
        if not num_link:
            continue
        number = num_link.get_text(strip=True)
        if not re.fullmatch(r"\d{3}", number):
            continue

        tds = tr.select("td")
        straight_count = None
        straight_amount = None
        count_td = tr.select_one("td.text-right.d-none.d-sm-table-cell")
        if count_td:
            cm = re.search(r"([\d,]+)\s*口", count_td.get_text())
            if cm:
                straight_count = int(cm.group(1).replace(",", ""))
        amount_td = tr.select_one("td.text-right.text-danger")
        if amount_td:
            am = re.search(r"([\d,]+)\s*円", amount_td.get_text())
            if am:
                straight_amount = int(am.group(1).replace(",", ""))

        rows.append({
            "draw_no": draw_no,
            "draw_date": draw_date,
            "number": number,
            "straight_count": straight_count,
            "straight_amount": straight_amount,
            "box_count": None,
            "box_amount": None,
            "set_straight_count": None,
            "set_straight_amount": None,
            "set_box_count": None,
            "set_box_amount": None,
            "mini_number": None,
            "mini_count": None,
            "mini_amount": None,
            "source": "scrape",
        })
    return rows


def parse_detail_page(html: str) -> dict:
    """詳細ページからボックス/セット/ミニの口数・金額を抽出する。"""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table.table-bordered")
    result = {
        "box_count": None, "box_amount": None,
        "set_straight_count": None, "set_straight_amount": None,
        "set_box_count": None, "set_box_amount": None,
        "mini_number": None, "mini_count": None, "mini_amount": None,
    }
    if not table:
        return result

    # モバイル表示用の短縮ラベル（"セット(s)"等）が別セルに入っており、
    # label列だけでは判定できない行があるため行全体のテキストに対する部分一致で判定する。
    # "ボックス"は"セットボックス"の部分文字列になるため、より具体的なラベルを先に判定する。
    label_priority = [
        ("セットストレート", ("set_straight_count", "set_straight_amount")),
        ("セットボックス", ("set_box_count", "set_box_amount")),
        ("ボックス", ("box_count", "box_amount")),
        ("ミニ", ("mini_count", "mini_amount")),
    ]
    for tr in table.select("tr"):
        tds = tr.select("td")
        if len(tds) < 3:
            continue
        row_text = tr.get_text()
        matched = next((key for key, _ in label_priority if key in row_text), None)
        if not matched:
            continue
        count_field, amount_field = dict(label_priority)[matched]

        cell_text = tr.get_text()
        cm = re.search(r"([\d,]+)\s*口", cell_text)
        am = re.search(r"([\d,]+)\s*円", cell_text)
        if cm:
            result[count_field] = int(cm.group(1).replace(",", ""))
        if am:
            result[amount_field] = int(am.group(1).replace(",", ""))

        if matched == "ミニ":
            mini_link = tr.select_one("a.num")
            if mini_link:
                mini_num = mini_link.get_text(strip=True)
                if re.fullmatch(r"\d{2}", mini_num):
                    result["mini_number"] = mini_num

    return result


def scrape_list(stop_at_draw_no: int, full: bool) -> list[dict]:
    collected = []
    page = 1
    while True:
        html = fetch(LIST_URL, params={"s": "desc", "l": 100, "page": page})
        rows = parse_list_page(html)
        if not rows:
            break
        new_rows = [r for r in rows if full or r["draw_no"] > stop_at_draw_no]
        collected.extend(new_rows)
        if not full and len(new_rows) < len(rows):
            break
        if len(rows) < 100:
            break
        page += 1
        time.sleep(REQUEST_INTERVAL_SEC)
    return collected


def enrich_rows(conn, limit: int | None) -> int:
    query = """
        SELECT draw_no FROM draws
        WHERE box_count IS NULL OR mini_number IS NULL
        ORDER BY draw_no DESC
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    draw_nos = [r[0] for r in conn.execute(query).fetchall()]

    updated = 0
    for draw_no in draw_nos:
        html = fetch(DETAIL_URL.format(draw_no=draw_no))
        detail = parse_detail_page(html)
        conn.execute(
            """UPDATE draws SET
                box_count=:box_count, box_amount=:box_amount,
                set_straight_count=:set_straight_count, set_straight_amount=:set_straight_amount,
                set_box_count=:set_box_count, set_box_amount=:set_box_amount,
                mini_number=:mini_number, mini_count=:mini_count, mini_amount=:mini_amount
               WHERE draw_no=:draw_no""",
            {**detail, "draw_no": draw_no},
        )
        conn.commit()
        updated += 1
        print(f"  補完完了: 第{draw_no}回")
        time.sleep(REQUEST_INTERVAL_SEC)
    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="DB内容を無視し一覧ページを末尾まで全取得")
    parser.add_argument("--enrich", action="store_true", help="box/set/miniが未取得のレコードを詳細ページから補完")
    parser.add_argument("--limit", type=int, default=None, help="--enrich時の処理件数上限")
    args = parser.parse_args()

    conn = connect()
    try:
        if args.enrich:
            print("詳細ページからボックス/セット/ミニを補完します...")
            n = enrich_rows(conn, args.limit)
            print(f"補完件数: {n}")
            return

        max_draw_no = get_max_draw_no(conn)
        print(f"DB内の最大回号: {max_draw_no}" if max_draw_no else "DBは空です（初回全件取得モード推奨: --full）")

        rows = scrape_list(stop_at_draw_no=max_draw_no, full=args.full)
        if not rows:
            print("新規データはありませんでした。")
            return

        n = upsert_draws(conn, rows)
        print(f"取得・登録件数: {n}（第{min(r['draw_no'] for r in rows)}回〜第{max(r['draw_no'] for r in rows)}回）")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
