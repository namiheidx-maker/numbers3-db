#!/usr/bin/env python3
"""schema.sql を読み込み、db/numbers3.db を初期化（既存なら差分適用）する。"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "numbers3.db"
SCHEMA_PATH = ROOT / "schema.sql"


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
        print(f"初期化完了: {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
