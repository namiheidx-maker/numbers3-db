#!/usr/bin/env python3
"""
data/ 配下のCSVファイルからナンバーズ3の当せんデータを取り込む。

期待するCSVヘッダー（1行目、過不足は自動対応）:
  回号,抽せん日,当選数字[,ストレート口数,ストレート金額,ボックス口数,ボックス金額,
         セットストレート口数,セットストレート金額,セットボックス口数,セットボックス金額,
         ミニ番号,ミニ口数,ミニ金額]
  - 「回号,抽せん日,当選数字」の3列のみあれば取り込み可能（他はNULLになる）
  - 列名は完全一致でなくてもよい（下記 HEADER_ALIASES で揺れを吸収）
  - 抽せん日は "YYYY-MM-DD" "YYYY/MM/DD" "YYYY年MM月DD日" のいずれかを想定

使い方:
  python3 import_csv.py data/numbers3_history.csv
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect, upsert_draws

HEADER_ALIASES = {
    "draw_no": ["回号", "抽せん回", "抽選回", "回数", "No", "draw_no"],
    "draw_date": ["抽せん日", "抽選日", "日付", "draw_date"],
    "number": ["当選数字", "当せん番号", "本数字", "ストレート", "number"],
    "straight_count": ["ストレート口数", "口数[ストレート]", "straight_count"],
    "straight_amount": ["ストレート金額", "ストレート当せん金額", "金額[ストレート]", "straight_amount"],
    "box_count": ["ボックス口数", "口数[ボックス]", "box_count"],
    "box_amount": ["ボックス金額", "ボックス当せん金額", "金額[ボックス]", "box_amount"],
    "set_straight_count": ["セットストレート口数", "口数[セット・ストレート]", "set_straight_count"],
    "set_straight_amount": ["セットストレート金額", "金額[セット・ストレート]", "set_straight_amount"],
    "set_box_count": ["セットボックス口数", "口数[セット・ボックス]", "set_box_count"],
    "set_box_amount": ["セットボックス金額", "金額[セット・ボックス]", "set_box_amount"],
    "mini_number": ["ミニ番号", "ミニ当選数字", "mini_number"],
    "mini_count": ["ミニ口数", "口数[ミニ]", "mini_count"],
    "mini_amount": ["ミニ金額", "金額[ミニ]", "mini_amount"],
}

REQUIRED = ["draw_no", "draw_date", "number"]
OPTIONAL_NUMERIC = [k for k in HEADER_ALIASES if k not in REQUIRED and not k.endswith("_number")]


def build_column_map(fieldnames: list[str]) -> dict[str, str]:
    """CSVの実際のヘッダー名 -> 内部フィールド名 の対応表を作る。"""
    normalized = {name.strip(): name for name in fieldnames}
    mapping = {}
    for internal, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[internal] = normalized[alias]
                break
    missing = [k for k in REQUIRED if k not in mapping]
    if missing:
        raise ValueError(
            f"必須列が見つかりません: {missing}\n"
            f"CSVのヘッダー: {fieldnames}\n"
            f"対応エイリアス一覧: {HEADER_ALIASES}"
        )
    return mapping


def normalize_date(raw: str) -> str:
    raw = raw.strip()
    m = re.match(r"(\d{4})[/年](\d{1,2})[/月](\d{1,2})日?", raw)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    raise ValueError(f"日付形式を解釈できません: {raw!r}")


def normalize_number(raw: str, width: int = 3) -> str:
    raw = raw.strip()
    if not re.fullmatch(r"\d{1,%d}" % width, raw):
        raise ValueError(f"数字形式を解釈できません: {raw!r}")
    return raw.zfill(width)


def to_int_or_none(raw: str | None):
    if raw is None:
        return None
    raw = raw.strip().replace(",", "")
    if raw == "":
        return None
    return int(raw)


def parse_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSVにヘッダー行がありません")
        colmap = build_column_map(reader.fieldnames)

        rows = []
        for i, raw_row in enumerate(reader, start=2):  # 1行目はヘッダーなのでデータは2行目から
            try:
                row = {
                    "draw_no": int(raw_row[colmap["draw_no"]].strip()),
                    "draw_date": normalize_date(raw_row[colmap["draw_date"]]),
                    "number": normalize_number(raw_row[colmap["number"]], width=3),
                    "source": "csv_import",
                }
                for field in OPTIONAL_NUMERIC:
                    row[field] = to_int_or_none(raw_row.get(colmap.get(field, ""), None)) if field in colmap else None
                row["mini_number"] = (
                    normalize_number(raw_row[colmap["mini_number"]], width=2)
                    if "mini_number" in colmap and raw_row.get(colmap["mini_number"], "").strip()
                    else None
                )
                rows.append(row)
            except Exception as e:
                raise ValueError(f"{path.name} {i}行目の取り込みに失敗: {e}") from e
        return rows


def main():
    if len(sys.argv) != 2:
        print(f"使い方: python3 {sys.argv[0]} <CSVファイルパス>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"ファイルが見つかりません: {path}")
        sys.exit(1)

    rows = parse_csv(path)
    print(f"読み込み件数: {len(rows)}")

    conn = connect()
    try:
        n = upsert_draws(conn, rows)
        print(f"登録件数: {n}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
