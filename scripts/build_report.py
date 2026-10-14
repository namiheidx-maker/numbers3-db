#!/usr/bin/env python3
"""
db/numbers3.db から当選台帳ダッシュボード（dashboard/report.html）を生成する。
Artifactとして公開/更新する直前に実行する想定。

構成:
  - 直近30回の当選数字（チップ一覧）＋「すべての当選履歴を見る」ボタン（全件モーダル）
  - ストレート当選傾向 上位10（＋「もっと見る」で上位50まで展開）
  ボックスは購入対象外のため非掲載。ストレート／セット購入向け。
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect
from analyze import format_date_ja

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "dashboard" / "report.html"

RECENT_N = 30
TOP_VISIBLE = 10
TOP_EXPANDED = 50
MIN_COUNT = 2

STYLE = """
<title>ナンバーズ3 当選台帳</title>
<style>
:root{
  color-scheme: light;
  --bg:#EFF1F6; --surface:#FFFFFF; --surface-2:#F3F4F8;
  --ink:#1B2338; --ink-dim:#5B6478; --ink-mute:#8891A3;
  --accent:#9A6A17; --accent-ink:#1B2338;
  --rule:#DDE1EA; --track:#E6E8EF; --overlay:rgba(20,24,38,.45);
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    color-scheme: dark;
    --bg:#121826; --surface:#1B2338; --surface-2:#222B42;
    --ink:#EDEFF5; --ink-dim:#9AA3B8; --ink-mute:#6E7792;
    --accent:#E8B34A; --accent-ink:#121826;
    --rule:#2E3850; --track:#2A3350; --overlay:rgba(6,9,18,.6);
  }
}
:root[data-theme="dark"]{
  color-scheme: dark;
  --bg:#121826; --surface:#1B2338; --surface-2:#222B42;
  --ink:#EDEFF5; --ink-dim:#9AA3B8; --ink-mute:#6E7792;
  --accent:#E8B34A; --accent-ink:#121826;
  --rule:#2E3850; --track:#2A3350; --overlay:rgba(6,9,18,.6);
}
*{box-sizing:border-box;}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:"Zen Kaku Gothic New","Hiragino Sans","Noto Sans JP",system-ui,sans-serif;
}
.page{max-width:1080px; margin:0 auto; padding:28px 20px 56px;}

.masthead{display:flex; align-items:center; gap:16px; margin-bottom:22px;}
.mark{
  width:52px; height:52px; flex:none; border-radius:12px;
  background:var(--surface-2); border:1px solid var(--rule);
  display:flex; align-items:center; justify-content:center;
  font-family:"IBM Plex Mono",monospace; font-weight:600; font-size:1.05rem; color:var(--accent);
}
.masthead-text{flex:1; min-width:0;}
.masthead-text h1{
  margin:0; font-size:clamp(1.4rem,2.6vw,1.9rem); font-weight:700;
  text-wrap:balance; letter-spacing:.01em;
}
.masthead-text p{margin:2px 0 0; color:var(--ink-dim); font-size:.92rem;}

.stamp{
  flex:none; display:flex; flex-direction:column; align-items:center; gap:2px;
  padding:10px 18px; border:2px solid var(--accent); border-radius:10px;
  background:var(--surface-2);
}
.stamp-label{font-size:.68rem; color:var(--ink-dim); letter-spacing:.12em;}
.stamp-value{
  font-family:"IBM Plex Mono",monospace; font-weight:700; font-size:1.15rem; color:var(--accent);
  font-variant-numeric:tabular-nums;
}
.stamp-date{font-size:.72rem; color:var(--ink-mute);}

.meta-row{
  display:flex; flex-wrap:wrap; gap:0; margin-bottom:26px;
  border:1px solid var(--rule); border-radius:10px; overflow:hidden; background:var(--surface);
}
.meta-item{
  flex:1; min-width:160px; padding:12px 18px; border-right:1px solid var(--rule);
  display:flex; flex-direction:column; gap:2px;
}
.meta-item:last-child{border-right:none;}
.meta-k{font-size:.72rem; color:var(--ink-dim); letter-spacing:.06em;}
.meta-v{
  font-family:"IBM Plex Mono",monospace; font-size:1rem; font-weight:600;
  font-variant-numeric:tabular-nums;
}

.section{background:var(--surface); border:1px solid var(--rule); border-radius:12px; overflow:hidden; margin-bottom:22px;}
.section-head{
  display:flex; align-items:baseline; justify-content:space-between; gap:12px;
  padding:16px 20px; border-bottom:1px solid var(--rule);
}
.section-head h2{margin:0; font-size:1.1rem; font-weight:700;}
.section-head p{margin:4px 0 0; font-size:.8rem; color:var(--ink-dim);}
.section-body{padding:18px 20px;}

.btn{
  display:inline-flex; align-items:center; gap:6px; flex:none;
  padding:7px 14px; border:1px solid var(--accent); border-radius:999px;
  background:transparent; color:var(--accent); font:inherit; font-weight:600; font-size:.78rem;
  cursor:pointer; white-space:nowrap;
}
.btn:hover{background:var(--surface-2);}
.btn:focus-visible{outline:2px solid var(--accent); outline-offset:2px;}
.btn-row{display:flex; justify-content:center; padding:14px 20px 18px; border-top:1px solid var(--rule);}

.strip{display:flex; flex-wrap:wrap; gap:8px;}
.chip{
  flex:none; width:76px; padding:8px 4px; border:1px solid var(--rule); border-radius:8px;
  background:var(--surface-2); text-align:center;
}
.chip-no{font-family:"IBM Plex Mono",monospace; font-size:.66rem; color:var(--ink-mute); font-variant-numeric:tabular-nums;}
.chip-number{
  font-family:"IBM Plex Mono",monospace; font-weight:600; font-size:1.15rem; color:var(--accent);
  font-variant-numeric:tabular-nums; margin:2px 0;
}
.chip-date{font-size:.62rem; color:var(--ink-mute);}

.ledger{display:flex; flex-direction:column;}
.row{
  display:grid; grid-template-columns:30px auto 1fr; align-items:center; gap:14px;
  padding:13px 20px; border-bottom:1px solid var(--rule);
}
.ledger > .row:last-child, .ledger > div:last-child .row:last-child{border-bottom:none;}
.row:hover{background:var(--surface-2);}
.rank{font-family:"IBM Plex Mono",monospace; font-size:.78rem; color:var(--ink-mute); font-variant-numeric:tabular-nums;}
.number{
  font-family:"IBM Plex Mono",monospace; font-weight:600; font-size:1.3rem;
  color:var(--accent); letter-spacing:.03em; font-variant-numeric:tabular-nums;
}
.row-detail{display:flex; flex-direction:column; gap:6px; min-width:0;}
.row-stats{display:flex; flex-wrap:wrap; gap:4px 12px; font-size:.82rem; color:var(--ink-dim);}
.row-stats b{color:var(--ink); font-weight:700;}
.row-stats small{color:var(--ink-mute);}
.meter{display:flex; align-items:center; gap:8px;}
.meter-track{flex:1; height:7px; background:var(--track); border-radius:4px; overflow:hidden;}
.meter-fill{height:100%; background:var(--accent); border-radius:0 4px 4px 0;}
.meter-value{
  font-family:"IBM Plex Mono",monospace; font-size:.74rem; color:var(--ink-dim);
  white-space:nowrap; min-width:72px; text-align:right; font-variant-numeric:tabular-nums;
}

.is-hidden{display:none !important;}

.overlay{
  position:fixed; inset:0; background:var(--overlay); display:flex;
  align-items:center; justify-content:center; padding:24px; z-index:10;
}
.dialog{
  background:var(--surface); border:1px solid var(--rule); border-radius:12px;
  width:min(640px,100%); max-height:min(80vh,720px); display:flex; flex-direction:column; overflow:hidden;
}
.dialog-head{display:flex; align-items:center; justify-content:space-between; padding:14px 20px; border-bottom:1px solid var(--rule);}
.dialog-head h2{margin:0; font-size:1rem; font-weight:700;}
.dialog-body{overflow-y:auto; padding:0;}
table.history{width:100%; border-collapse:collapse;}
table.history th, table.history td{
  padding:9px 20px; text-align:left; font-size:.85rem; border-bottom:1px solid var(--rule);
}
table.history th{
  position:sticky; top:0; background:var(--surface); color:var(--ink-dim);
  font-size:.72rem; letter-spacing:.04em; font-weight:600;
}
table.history td.num{font-family:"IBM Plex Mono",monospace; color:var(--accent); font-weight:600; font-variant-numeric:tabular-nums;}
table.history td.no{font-family:"IBM Plex Mono",monospace; color:var(--ink-mute); font-variant-numeric:tabular-nums;}

.note{margin-top:4px; padding:16px 20px 0; border-top:1px solid var(--rule);}
.note p{margin:0; max-width:68ch; font-size:.78rem; color:var(--ink-mute); line-height:1.6;}

@media (prefers-reduced-motion: reduce){ *{scroll-behavior:auto !important;} }
</style>
"""

HEAD_LINK = (
    '<link rel="stylesheet" '
    'href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700;900'
    '&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap">'
)

SCRIPT = """
<script>
function toggleExtra(id, btn, moreLabel, lessLabel){
  var el = document.getElementById(id);
  var hidden = el.classList.toggle('is-hidden');
  btn.textContent = hidden ? moreLabel : lessLabel;
}
function toggleHistory(show){
  var el = document.getElementById('history-overlay');
  if(show){ el.classList.remove('is-hidden'); }
  else { el.classList.add('is-hidden'); }
}
</script>
"""


def chip_html(draw_no: int, draw_date: str, number: str) -> str:
    return f"""<div class="chip">
  <div class="chip-no">第{draw_no}回</div>
  <div class="chip-number">{number}</div>
  <div class="chip-date">{format_date_ja(draw_date)}</div>
</div>"""


def row_html(rank: int, key: str, win_count: int, last_win_draw_no: int,
             last_win_date: str, draws_elapsed: int, max_elapsed: int) -> str:
    pct = max(3, round(draws_elapsed / max_elapsed * 100)) if max_elapsed > 0 else 3
    return f"""<div class="row">
  <span class="rank">{rank:02d}</span>
  <span class="number">{key}</span>
  <div class="row-detail">
    <div class="row-stats"><b>{win_count}回</b>当選　最終 第{last_win_draw_no}回<small>（{format_date_ja(last_win_date)}）</small></div>
    <div class="meter">
      <div class="meter-track"><div class="meter-fill" style="width:{pct}%"></div></div>
      <span class="meter-value">{draws_elapsed}回経過</span>
    </div>
  </div>
</div>"""


def history_row_html(draw_no: int, draw_date: str, number: str) -> str:
    return (f'<tr><td class="no">第{draw_no}回</td>'
            f'<td>{format_date_ja(draw_date)}</td>'
            f'<td class="num">{number}</td></tr>')


def main():
    conn = connect()
    try:
        total, min_date, max_date = conn.execute(
            "SELECT COUNT(*), MIN(draw_date), MAX(draw_date) FROM draws"
        ).fetchone()
        latest_draw_no = conn.execute("SELECT MAX(draw_no) FROM draws").fetchone()[0]

        recent = conn.execute(
            "SELECT draw_no, draw_date, number FROM draws ORDER BY draw_no DESC LIMIT ?",
            (RECENT_N,),
        ).fetchall()

        straight = conn.execute(
            """SELECT * FROM v_number_stats WHERE win_count >= ?
               ORDER BY win_count DESC, last_win_draw_no ASC LIMIT ?""",
            (MIN_COUNT, TOP_EXPANDED),
        ).fetchall()

        all_draws = conn.execute(
            "SELECT draw_no, draw_date, number FROM draws ORDER BY draw_no DESC"
        ).fetchall()
    finally:
        conn.close()

    today_ja = format_date_ja(date.today().isoformat())

    chips = "\n".join(chip_html(*r) for r in recent)

    elapsed_list = [latest_draw_no - r[3] for r in straight]
    max_elapsed = max(elapsed_list) if elapsed_list else 1

    visible_rows, extra_rows = [], []
    for rank, (key, win_count, last_win_date, last_win_draw_no, _days) in enumerate(straight, start=1):
        draws_elapsed = latest_draw_no - last_win_draw_no
        html = row_html(rank, key, win_count, last_win_draw_no, last_win_date, draws_elapsed, max_elapsed)
        (visible_rows if rank <= TOP_VISIBLE else extra_rows).append(html)

    history_rows = "\n".join(history_row_html(*r) for r in all_draws)

    body = f"""{STYLE}
{HEAD_LINK}
<div class="page">
  <header class="masthead">
    <div class="mark">N3</div>
    <div class="masthead-text">
      <h1>当選台帳</h1>
      <p>ナンバーズ3 ストレート・セット購入向けトラッカー</p>
    </div>
    <div class="stamp">
      <span class="stamp-label">最新回号</span>
      <span class="stamp-value">第{latest_draw_no}回</span>
      <span class="stamp-date">{format_date_ja(max_date)}</span>
    </div>
  </header>

  <div class="meta-row">
    <div class="meta-item"><span class="meta-k">総抽せん回数</span><span class="meta-v">{total}回</span></div>
    <div class="meta-item"><span class="meta-k">収録期間</span><span class="meta-v" style="font-size:.85rem">{format_date_ja(min_date)} 〜 {format_date_ja(max_date)}</span></div>
    <div class="meta-item"><span class="meta-k">更新日</span><span class="meta-v">{today_ja}</span></div>
  </div>

  <section class="section">
    <div class="section-head">
      <div>
        <h2>直近{RECENT_N}回の当選数字</h2>
        <p>新しい回ほど左上・第{latest_draw_no}回から遡って{RECENT_N}回分</p>
      </div>
    </div>
    <div class="section-body">
      <div class="strip">
{chips}
      </div>
    </div>
    <div class="btn-row">
      <button class="btn" onclick="toggleHistory(true)">すべての当選履歴を見る（全{total}回）</button>
    </div>
  </section>

  <section class="section">
    <div class="section-head">
      <div>
        <h2>ストレート当選傾向</h2>
        <p>並び順まで一致・当選回数が多い順（上位{TOP_VISIBLE}）</p>
      </div>
    </div>
    <div class="ledger">
{chr(10).join(visible_rows)}
      <div id="straight-extra" class="is-hidden">
{chr(10).join(extra_rows)}
      </div>
    </div>
    <div class="btn-row">
      <button class="btn" onclick="toggleExtra('straight-extra', this, '上位{TOP_EXPANDED}まで見る', '閉じる')">上位{TOP_EXPANDED}まで見る</button>
    </div>
  </section>

  <footer class="note">
    <p>各回の抽せんは独立試行です。出現回数・経過回数は過去{total}回の実績に生じた数字の偏り（サンプリング変動）の可視化であり、将来の当せんを予測するものではありません。ボックスは購入対象外のため非掲載（ストレート／セット購入向け）。</p>
  </footer>
</div>

<div id="history-overlay" class="overlay is-hidden">
  <div class="dialog">
    <div class="dialog-head">
      <h2>全当選履歴（第1回〜第{latest_draw_no}回・{total}回）</h2>
      <button class="btn" onclick="toggleHistory(false)">閉じる</button>
    </div>
    <div class="dialog-body">
      <table class="history">
        <thead><tr><th>回号</th><th>抽せん日</th><th>当選数字</th></tr></thead>
        <tbody>
{history_rows}
        </tbody>
      </table>
    </div>
  </div>
</div>
{SCRIPT}
"""

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(body, encoding="utf-8")
    print(f"生成完了: {OUT_PATH}（{OUT_PATH.stat().st_size:,} bytes）")


if __name__ == "__main__":
    main()
