"""import_csv.py / scrape_update.py で共有するDB書き込みロジック。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "numbers3.db"

_UPSERT_SQL = """
INSERT INTO draws (
    draw_no, draw_date, number, box_key,
    straight_count, straight_amount,
    box_count, box_amount,
    set_straight_count, set_straight_amount,
    set_box_count, set_box_amount,
    mini_number, mini_count, mini_amount,
    source
) VALUES (
    :draw_no, :draw_date, :number, :box_key,
    :straight_count, :straight_amount,
    :box_count, :box_amount,
    :set_straight_count, :set_straight_amount,
    :set_box_count, :set_box_amount,
    :mini_number, :mini_count, :mini_amount,
    :source
)
ON CONFLICT(draw_no) DO UPDATE SET
    draw_date=excluded.draw_date, number=excluded.number, box_key=excluded.box_key,
    straight_count=COALESCE(excluded.straight_count, draws.straight_count),
    straight_amount=COALESCE(excluded.straight_amount, draws.straight_amount),
    box_count=COALESCE(excluded.box_count, draws.box_count),
    box_amount=COALESCE(excluded.box_amount, draws.box_amount),
    set_straight_count=COALESCE(excluded.set_straight_count, draws.set_straight_count),
    set_straight_amount=COALESCE(excluded.set_straight_amount, draws.set_straight_amount),
    set_box_count=COALESCE(excluded.set_box_count, draws.set_box_count),
    set_box_amount=COALESCE(excluded.set_box_amount, draws.set_box_amount),
    mini_number=COALESCE(excluded.mini_number, draws.mini_number),
    mini_count=COALESCE(excluded.mini_count, draws.mini_count),
    mini_amount=COALESCE(excluded.mini_amount, draws.mini_amount),
    source=excluded.source
"""

_FIELDS = (
    "draw_no", "draw_date", "number", "straight_count", "straight_amount",
    "box_count", "box_amount", "set_straight_count", "set_straight_amount",
    "set_box_count", "set_box_amount", "mini_number", "mini_count", "mini_amount",
    "source",
)


def box_key_of(number: str) -> str:
    """numberの3桁を昇順ソートした文字列を返す（例: "552" -> "255"）。"""
    return "".join(sorted(number))


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """テーブルとビューがなければ初期化"""
    conn = connect()
    try:
        conn.execute("SELECT 1 FROM draws LIMIT 1")
    except sqlite3.OperationalError:
        schema_path = ROOT / "schema.sql"
        with open(schema_path) as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)
    finally:
        conn.close()


def upsert_draws(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """rows の各要素は _FIELDS のキーを持つ dict。number から box_key を自動算出して書き込む。
    戻り値: 書き込んだ件数。
    """
    records = []
    for row in rows:
        missing = [f for f in _FIELDS if f not in row]
        if missing:
            raise ValueError(f"必須フィールド欠落: {missing} (draw_no={row.get('draw_no')})")
        record = {f: row[f] for f in _FIELDS}
        record["box_key"] = box_key_of(record["number"])
        records.append(record)

    conn.executemany(_UPSERT_SQL, records)
    conn.commit()
    return len(records)


def get_max_draw_no(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()
    return row[0] if row and row[0] is not None else 0
