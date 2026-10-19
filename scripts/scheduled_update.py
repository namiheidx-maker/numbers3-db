#!/usr/bin/env python3
"""
スケジュール付きデータ更新

実行スケジュール:
  月～金:
    - 09:00以降: 最新のデータが取得できていなければ取得
    - 18:00以降: 当日のデータが取得できていなければ取得
  土:
    - 09:00以降: 最新のデータが取得できていなければ取得
  日:
    - 09:00以降: 最新のデータが取得できていなければ取得

推奨 crontab 設定:
  0 9 * * 1-7 cd /path/to/numbers3-db && python3 scripts/scheduled_update.py
  0 18 * * 1-5 cd /path/to/numbers3-db && python3 scripts/scheduled_update.py
"""
from datetime import datetime, date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect, get_max_draw_no, init_db
import update_data


def should_update(conn):
    """更新が必要かどうかを判定"""
    now = datetime.now()
    today = now.date()
    weekday = today.weekday()  # 0=月, 1=火, ..., 6=日

    max_draw_no = get_max_draw_no(conn)
    if max_draw_no == 0:
        # データベースが空の場合は常に更新
        return True, "データベースが空"

    # 最新のデータから当選日を取得
    latest_draw = conn.execute(
        "SELECT draw_no, draw_date FROM draws WHERE draw_no = ?", (max_draw_no,)
    ).fetchone()

    if not latest_draw:
        return True, "最新データなし"

    latest_draw_date = date.fromisoformat(latest_draw[1])

    # 時刻別の判定
    current_hour = now.hour

    if weekday <= 4:  # 月～金
        if current_hour >= 18:
            # 夜18時以降：当日のデータが必要
            if latest_draw_date == today:
                return False, "当日のデータ取得済み"
            else:
                return True, "当日のデータを取得"
        elif current_hour >= 9:
            # 朝9時以降（18時未満）：最新のデータが必要
            # 営業日は前営業日のデータが最新のはず
            # ただし、当日はまだ抽せんがない時間帯
            if latest_draw_date == today:
                # 当日はまだデータが出ていないはずだが、出ている場合は不要
                return False, "当日データ既に取得"
            elif latest_draw_date == latest_weekday(today, -1):
                # 前営業日のデータがある場合は不要
                return False, "前営業日のデータ取得済み"
            else:
                # それより古い場合は更新
                return True, "古いデータを更新"
        else:
            # 朝9時未満：更新しない
            return False, "時刻外"
    else:  # 土日
        if current_hour >= 9:
            # 土日の朝9時以降：最新のデータが必要（金曜のデータ）
            if latest_draw_date == latest_weekday(today, -2):
                # 金曜のデータがある場合は不要
                return False, "金曜のデータ取得済み"
            else:
                return True, "古いデータを更新"
        else:
            # 朝9時未満：更新しない
            return False, "時刻外"


def latest_weekday(d: date, days_offset: int = -1) -> date:
    """最新の営業日を取得（d から days_offset 営業日前）

    days_offset = -1: 前営業日
    days_offset = -2: 2営業日前（金曜から見ると前回の金曜）
    """
    current = d
    remaining = abs(days_offset)
    direction = -1 if days_offset < 0 else 1

    while remaining > 0:
        current = date(current.year, current.month, current.day)
        from datetime import timedelta
        current = current + timedelta(days=direction)
        if current.weekday() <= 4:  # 月～金
            remaining -= 1

    return current


def main():
    init_db()
    conn = connect()
    try:
        should_upd, reason = should_update(conn)

        if not should_upd:
            print(f"[スキップ] {reason}")
            sys.exit(0)

        print(f"[更新開始] {reason}")
        update_data.main()
        print("[完了]")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
