"""pickupsテーブル（過去のピックアップ予想記録）をJSONファイルと同期する。

drawsテーブルはmk-mode.comのCSV再取得で毎回完全に再構築できるためdb/numbers3.db自体は
.gitignore対象（環境ごとに独立していてよい）だが、pickupsは「その時点でどの番号を
予想したか」という再現不可能な一次記録であり、ローカル環境とGitHub Actions環境で
別々のdb/numbers3.dbを持つ構成だと記録が食い違ってしまう（2026-10-26に実際発生）。

data/pickups.json（git管理）を正本として、save_pickup()の実行前にインポート、
実行後にエクスポートすることで環境間の記録を合流させる。
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PICKUPS_JSON_PATH = ROOT / "data" / "pickups.json"

_COLUMNS = ("based_on_draw_no", "rank", "number", "box_key", "win_count", "avg_interval", "draws_elapsed")


def import_pickups_from_json(conn: sqlite3.Connection) -> int:
    """data/pickups.json の内容をpickupsテーブルへ取り込む（同一キーは上書き）。"""
    if not PICKUPS_JSON_PATH.exists():
        return 0
    data = json.loads(PICKUPS_JSON_PATH.read_text(encoding="utf-8"))
    conn.executemany(
        f"INSERT OR REPLACE INTO pickups ({', '.join(_COLUMNS)}) "
        f"VALUES ({', '.join('?' for _ in _COLUMNS)})",
        [tuple(row[c] for c in _COLUMNS) for row in data],
    )
    conn.commit()
    return len(data)


def export_pickups_to_json(conn: sqlite3.Connection) -> int:
    """pickupsテーブルの全件をdata/pickups.jsonへ書き出す。"""
    rows = conn.execute(
        f"SELECT {', '.join(_COLUMNS)} FROM pickups ORDER BY based_on_draw_no, rank"
    ).fetchall()
    data = [dict(zip(_COLUMNS, row)) for row in rows]
    PICKUPS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    PICKUPS_JSON_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(data)
