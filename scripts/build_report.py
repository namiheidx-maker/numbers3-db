#!/usr/bin/env python3
"""
db/numbers3.db から当選台帳ダッシュボード（dashboard/report.html）を生成する。
Artifactとして公開/更新する直前に実行する想定。

構成:
  - 直近30回の当選数字（チップ一覧・前回当選間隔の平均/最短/最長）＋「すべての当選履歴を見る」ボタン（全件モーダル）
  - ストレート当選傾向 上位10（＋「もっと見る」で上位/下位50まで展開）
    降順（上位50）／昇順（上位50）／昇順（全件の下から）の3モード切替・除外中の表示/非表示切替
  ボックスは購入対象外のため非掲載。ストレート／セット購入向け。
"""
from __future__ import annotations

import itertools
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_common import connect
from analyze import format_date_ja
from predict import get_candidates, get_pickup_candidates, save_pickup

PICKUP_VISIBLE = 5
PICKUP_EXPANDED = 30

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
  --accent:#9A6A17; --accent-ink:#FFFFFF;
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
.mode-btn.is-active{background:var(--accent); color:var(--accent-ink);}
.btn-row{display:flex; justify-content:center; padding:14px 20px 18px; border-top:1px solid var(--rule);}

.gap-summary{display:flex; flex-wrap:wrap; gap:0; margin-bottom:14px; border:1px solid var(--rule); border-radius:10px; overflow:hidden;}
.gap-stat{flex:1; min-width:160px; padding:10px 16px; border-right:1px solid var(--rule); background:var(--surface-2);}
.gap-stat:last-child{border-right:none;}
.gap-k{font-size:.7rem; color:var(--ink-dim); letter-spacing:.06em;}
.gap-v{
  display:block; font-family:"IBM Plex Mono",monospace; font-weight:700; font-size:1.05rem;
  color:var(--accent); font-variant-numeric:tabular-nums; margin-top:2px;
}
.gap-note{display:block; font-size:.7rem; color:var(--ink-mute); margin-top:2px;}

.strip{display:flex; flex-wrap:wrap; gap:8px;}
.chip{
  flex:none; width:128px; padding:9px 6px; border:1px solid var(--rule); border-radius:8px;
  background:var(--surface-2); text-align:center;
}
.chip-no{font-family:"IBM Plex Mono",monospace; font-size:.66rem; color:var(--ink-mute); font-variant-numeric:tabular-nums;}
.chip-number{
  font-family:"IBM Plex Mono",monospace; font-weight:600; font-size:1.15rem; color:var(--accent);
  font-variant-numeric:tabular-nums; margin:2px 0;
}
.chip-date{font-size:.62rem; color:var(--ink-mute);}
.chip-prev{
  margin-top:7px; padding-top:7px; border-top:1px dashed var(--rule);
  font-size:.62rem; color:var(--ink-mute); line-height:1.6;
}
.chip-prev b{color:var(--ink-dim); font-weight:700;}

.ledger{display:flex; flex-direction:column;}
.row{
  display:grid; grid-template-columns:30px auto 1fr auto; align-items:center; gap:14px;
  padding:13px 20px; border-bottom:1px solid var(--rule);
}
.ledger > .row:last-child, .ledger > div:last-child .row:last-child{border-bottom:none;}
.row:hover{background:var(--surface-2);}
.rank{font-family:"IBM Plex Mono",monospace; font-size:.78rem; color:var(--ink-mute); font-variant-numeric:tabular-nums;}
.number{
  font-family:"IBM Plex Mono",monospace; font-weight:600; font-size:1.3rem;
  color:var(--accent); letter-spacing:.03em; font-variant-numeric:tabular-nums;
}
.badge{
  flex:none; font-size:.66rem; font-weight:700; letter-spacing:.04em;
  padding:3px 8px; border-radius:999px; white-space:nowrap;
}
.badge-candidate{color:var(--accent); background:color-mix(in srgb, var(--accent) 16%, transparent); border:1px solid color-mix(in srgb, var(--accent) 45%, transparent);}
.badge-excluded{color:var(--ink-mute); background:var(--surface-2); border:1px solid var(--rule);}
.badge-hit{color:#fff; background:#1E8E5A; border:1px solid #1E8E5A;}
.badge-boxhit{color:#fff; background:#8A6D1E; border:1px solid #8A6D1E;}
.badge-miss{color:var(--ink-mute); background:var(--surface-2); border:1px solid var(--rule);}
.badge-pending{color:var(--ink-dim); background:var(--surface-2); border:1px solid var(--rule);}
.badge-type{color:var(--ink-dim); background:var(--surface); border:1px solid var(--rule);}
.badge-group{color:var(--accent); background:color-mix(in srgb, var(--accent) 14%, transparent); border:1px solid color-mix(in srgb, var(--accent) 40%, transparent);}
.buy-number{
  font-family:"IBM Plex Mono",monospace; font-weight:700; color:var(--accent);
  font-variant-numeric:tabular-nums; margin:0 10px 0 4px;
}

.pickup-summary{display:flex; flex-wrap:wrap; gap:0; margin-bottom:14px; border:1px solid var(--rule); border-radius:10px; overflow:hidden;}
.pickup-card{border:1px solid var(--rule); border-radius:10px; padding:12px 16px; margin-bottom:10px; background:var(--surface-2);}
.pickup-card:last-child{margin-bottom:0;}
.pickup-card-head{display:flex; flex-wrap:wrap; align-items:center; gap:8px; font-size:.84rem; color:var(--ink-dim); margin-bottom:8px;}
.pickup-card-head b{color:var(--ink); font-weight:700;}
.pickup-numbers{display:flex; flex-wrap:wrap; gap:6px;}
.pickup-chip{
  font-family:"IBM Plex Mono",monospace; font-weight:600; font-size:.9rem;
  padding:4px 9px; border-radius:7px; background:var(--surface); border:1px solid var(--rule);
  color:var(--ink-dim); font-variant-numeric:tabular-nums;
}
.pickup-chip-hit{color:#fff; background:#1E8E5A; border-color:#1E8E5A;}
.pickup-chip-boxhit{color:#fff; background:#8A6D1E; border-color:#8A6D1E;}
.ledger.hide-excluded .row-excluded{display:none;}
.section-head-actions{display:flex; flex-wrap:wrap; gap:8px; flex:none;}
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

.misc-row{font-size:.84rem; color:var(--ink-dim); line-height:1.8;}
.misc-row + .misc-row{margin-top:10px;}
.misc-row b{color:var(--ink); font-weight:700;}

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
function toggleExcluded(ids, btn, hideLabel, showLabel){
  var hidden = false;
  ids.forEach(function(id){
    hidden = document.getElementById(id).classList.toggle('hide-excluded');
  });
  btn.textContent = hidden ? showLabel : hideLabel;
}
function toggleHistory(show){
  var el = document.getElementById('history-overlay');
  if(show){ el.classList.remove('is-hidden'); }
  else { el.classList.add('is-hidden'); }
}
function reorderLedger(ledgerId, extraId, visibleCount, wantAsc){
  var ledger = document.getElementById(ledgerId);
  if((ledger.dataset.asc === 'true') === wantAsc) return;
  var extra = document.getElementById(extraId);
  var rows = Array.prototype.slice.call(ledger.querySelectorAll('.row'));
  rows.reverse();
  rows.forEach(function(row, i){
    var rankEl = row.querySelector('.rank');
    if(rankEl){ rankEl.textContent = String(i + 1).padStart(2, '0'); }
    if(i < visibleCount){ ledger.insertBefore(row, extra); }
    else { extra.appendChild(row); }
  });
  ledger.dataset.asc = wantAsc ? 'true' : 'false';
}
function setStraightMode(mode, btn){
  document.querySelectorAll('.mode-btn').forEach(function(b){ b.classList.remove('is-active'); });
  btn.classList.add('is-active');
  var top = document.getElementById('straight-ledger-top');
  var bottom = document.getElementById('straight-ledger-bottom');
  var moreTopRow = document.getElementById('straight-more-top-row');
  var moreBottomRow = document.getElementById('straight-more-bottom-row');
  if(mode === 'asc-bottom'){
    top.classList.add('is-hidden');
    bottom.classList.remove('is-hidden');
    moreTopRow.classList.add('is-hidden');
    moreBottomRow.classList.remove('is-hidden');
  } else {
    bottom.classList.add('is-hidden');
    top.classList.remove('is-hidden');
    moreBottomRow.classList.add('is-hidden');
    moreTopRow.classList.remove('is-hidden');
    reorderLedger('straight-ledger-top', 'straight-extra-top', 10, mode === 'asc-top');
  }
}
</script>
"""


def chip_html(draw_no: int, draw_date: str, number: str,
              prev_draw_no: int | None, prev_draw_date: str | None, gap: int | None) -> str:
    if prev_draw_no is None:
        prev_html = '<div class="chip-prev">初当選（前回なし）</div>'
    else:
        prev_html = (
            f'<div class="chip-prev">（前回）第{prev_draw_no}回<br>'
            f'{format_date_ja(prev_draw_date)}<br>'
            f'<b>前回より{gap}回経過</b></div>'
        )
    return f"""<div class="chip">
  <div class="chip-no">第{draw_no}回</div>
  <div class="chip-number">{number}</div>
  <div class="chip-date">{format_date_ja(draw_date)}</div>
  {prev_html}
</div>"""


def gap_summary_html(recent: list[tuple]) -> str:
    """recent（[draw_no, draw_date, number, prev_draw_no, prev_draw_date, gap], ...）から
    直近N回ぶんの「前回当選から今回当選までの経過」の平均・最短・最長をまとめたHTMLを返す。
    gapがNone（初当選で比較対象が無い行）は集計から除外する。
    """
    gapped = [r for r in recent if r[5] is not None]
    if not gapped:
        return ('<div class="gap-summary"><div class="gap-stat">'
                '<span class="gap-k">前回間隔</span><span class="gap-v">データ不足</span></div></div>')

    avg_gap = sum(r[5] for r in gapped) / len(gapped)
    min_row = min(gapped, key=lambda r: r[5])
    max_row = max(gapped, key=lambda r: r[5])

    def note(r):
        _draw_no, _draw_date, number, prev_draw_no, _prev_date, gap = r
        return f"{number}（第{prev_draw_no}回→第{_draw_no}回）"

    return f"""<div class="gap-summary">
  <div class="gap-stat"><span class="gap-k">平均間隔</span><span class="gap-v">{avg_gap:.1f}回</span></div>
  <div class="gap-stat"><span class="gap-k">最短間隔</span><span class="gap-v">{min_row[5]}回</span><span class="gap-note">{note(min_row)}</span></div>
  <div class="gap-stat"><span class="gap-k">最長間隔</span><span class="gap-v">{max_row[5]}回</span><span class="gap-note">{note(max_row)}</span></div>
</div>"""


def no_data_section_html(zero_win_numbers: list[str], one_win_rows: list[tuple]) -> str:
    """当選回数0〜1回で平均間隔を算出できない番号（ストレート当選傾向には出てこない）を列挙する。"""
    zero_html = "、".join(zero_win_numbers) if zero_win_numbers else "（該当なし）"
    one_html = "、".join(
        f"{number}（第{draw_no}回・{format_date_ja(draw_date)}）"
        for number, draw_no, draw_date in one_win_rows
    ) if one_win_rows else "（該当なし）"
    return f"""<section class="section">
    <div class="section-head">
      <div>
        <h2>判定対象外（データ不足）</h2>
        <p>当選回数が0〜1回で平均間隔を算出できない番号。上の「ストレート当選傾向」には含まれません</p>
      </div>
    </div>
    <div class="section-body">
      <div class="misc-row"><b>当選0回（一度も当選なし・{len(zero_win_numbers)}件）</b>：{zero_html}</div>
      <div class="misc-row"><b>当選1回（間隔のサンプルが無く算出不可・{len(one_win_rows)}件）</b>：{one_html}</div>
    </div>
  </section>"""


def group_pickup_rows(pickup_rows: list[tuple]) -> list[dict]:
    """v_pickup_results の行（based_on_draw_no DESC, rank ASC順）をbased_on_draw_noごとにまとめる。
    1タプル = (based_on_draw_no, target_draw_no, rank, picked_number, picked_box_key,
               win_count, avg_interval, draws_elapsed,
               target_draw_date, actual_number, actual_box_key, straight_hit, box_hit)
    """
    groups = []
    for based_on_draw_no, rows_iter in itertools.groupby(pickup_rows, key=lambda r: r[0]):
        rows = list(rows_iter)
        first = rows[0]
        groups.append({
            "based_on_draw_no": based_on_draw_no,
            "target_draw_no": first[1],
            "target_draw_date": first[8],
            "actual_number": first[9],
            "actual_box_key": first[10],
            "picks": rows,
        })
    return groups


def next_business_day(d: date) -> date:
    """ナンバーズ3は月〜金開催（土日は開催なし）のため、翌営業日を返す。
    祝日は考慮しない（休催日はupdate_data.py実行時の実データで初めて判明するため、
    ここでの日付は「土日を除けば次に来るはずの日」という見込みにとどまる）。
    """
    nxt = d + timedelta(days=1)
    while nxt.weekday() >= 5:  # 5=土, 6=日
        nxt += timedelta(days=1)
    return nxt


def digit_type_label(number: str) -> str:
    """同じ数字が何個含まれるかで「シングル目／ダブル目／トリプル目」を判定する。
    ボックス／セットボックスで的中した場合の配当倍率に関わる（並び方の数が変わるため）。
    """
    distinct = len(set(number))
    if distinct == 1:
        return "トリプル目"
    if distinct == 2:
        return "ダブル目"
    return "シングル目"


def group_by_box_key(group: dict) -> dict:
    """今日のピックアップをbox_key（3桁を昇順ソートした文字列）でグルーピングする。
    同じbox_keyを持つ候補は、どちらか一方をセットで買えば並び順違いの他方もセットボックスで
    カバーできる（セット購入はストレート一致＋ボックス一致の両方を1枚でカバーするため）。
    戻り値: {box_key: [picked_number, ...]}（グループ内は候補リストでの順位順）
    """
    by_box = {}
    for r in group["picks"]:
        picked_number, picked_box_key = r[3], r[4]
        by_box.setdefault(picked_box_key, []).append(picked_number)
    return by_box


def today_pickup_table_html(group: dict, latest_draw_date: str) -> str:
    """今日のピックアップ数字を順位付きで一覧表示し、セット購入でまとめてカバーできる
    組み合わせ（同じbox_keyを持つ候補どうし）があればヒントとして添える。
    """
    by_box = group_by_box_key(group)
    number_to_partners = {}
    for box_key, numbers in by_box.items():
        if len(numbers) > 1:
            for n in numbers:
                number_to_partners[n] = [x for x in numbers if x != n]

    rows = []
    for r in group["picks"]:
        _b, _t, rank, picked_number, _box, win_count, avg_interval, draws_elapsed, *_rest = r
        partners = number_to_partners.get(picked_number)
        cover_badge = (f'<span class="badge badge-group">セットで{"・".join(partners)}もカバー</span>'
                        if partners else "")
        rows.append(f"""<div class="row">
  <span class="rank">{rank:02d}</span>
  <span class="number">{picked_number}</span>
  <div class="row-detail">
    <div class="row-stats"><b>{win_count}回</b>当選　平均間隔{avg_interval:.1f}回　{draws_elapsed}回経過で選出　<span class="badge badge-type">{digit_type_label(picked_number)}</span></div>
  </div>
  {cover_badge}
</div>""")

    cover_groups = {bk: ns for bk, ns in by_box.items() if len(ns) > 1}
    if cover_groups:
        lines = "".join(
            f'<li><b class="buy-number">{numbers[0]}</b>をセットで買えば'
            f'{"・".join(numbers[1:])}もまとめてカバー（組み合わせ: {box_key}）</li>'
            for box_key, numbers in cover_groups.items()
        )
        saved = sum(len(ns) - 1 for ns in cover_groups.values())
        hint = f"""<div class="misc-row" style="margin-bottom:14px">
  <b>セット購入のまとめ買いヒント</b>：並び順違いで同じ3桁の組み合わせを持つ候補があります。
  セットはストレート一致・ボックス一致の両方を1枚でカバーするため、どちらか一方だけ買えば十分です。
  <ul style="margin:6px 0 0; padding-left:1.4em">{lines}</ul>
  実質的な購入数は{len(group['picks'])}個→{len(by_box)}個に減らせます（{saved}個分の重複を節約）。
</div>"""
    else:
        hint = ""

    next_date = next_business_day(date.fromisoformat(latest_draw_date))
    header = (f'<div class="misc-row" style="margin-bottom:10px">'
               f'<b>第{group["target_draw_no"]}回</b>の予想'
               f'（次回開催日: {format_date_ja(next_date.isoformat())}・月〜金開催のため予定、'
               f'第{group["based_on_draw_no"]}回時点のデータで算出）'
               f'</div>')
    return f"""{header}{hint}<div class="ledger">
{chr(10).join(rows)}
</div>"""


def pickup_card_html(group: dict) -> str:
    has_result = group["actual_number"] is not None
    any_straight_hit = has_result and any(r[11] for r in group["picks"])
    any_box_hit = has_result and any(r[12] for r in group["picks"])

    if not has_result:
        status = '<span class="badge badge-pending">結果待ち</span>'
        result_text = ""
    else:
        result_text = f'→ 実際: <b>{group["actual_number"]}</b>（{format_date_ja(group["target_draw_date"])}）'
        if any_straight_hit:
            status = '<span class="badge badge-hit">ストレート的中</span>'
        elif any_box_hit:
            status = '<span class="badge badge-boxhit">ボックス一致</span>'
        else:
            status = '<span class="badge badge-miss">不的中</span>'

    chips = []
    for r in group["picks"]:
        _b, _t, _rank, picked_number, _box, _wc, _avg, _elapsed, _date, _actual, _abox, straight_hit, box_hit = r
        if has_result and straight_hit:
            cls = "pickup-chip pickup-chip-hit"
        elif has_result and box_hit:
            cls = "pickup-chip pickup-chip-boxhit"
        else:
            cls = "pickup-chip"
        chips.append(f'<span class="{cls}">{_rank}. {picked_number}</span>')

    return f"""<div class="pickup-card">
  <div class="pickup-card-head">
    <b>第{group['target_draw_no']}回</b>の予想（第{group['based_on_draw_no']}回時点算出）{result_text}
    {status}
  </div>
  <div class="pickup-numbers">
{''.join(chips)}
  </div>
</div>"""


def pickup_summary_html(groups: list[dict]) -> str:
    evaluated = [g for g in groups if g["actual_number"] is not None]
    if not evaluated:
        return ('<div class="gap-summary"><div class="gap-stat">'
                '<span class="gap-k">評価済み</span><span class="gap-v">まだ結果が出ていません</span></div></div>')
    n = len(evaluated)
    straight_hits = sum(1 for g in evaluated if any(r[11] for r in g["picks"]))
    box_hits = sum(1 for g in evaluated if any(r[12] for r in g["picks"]))
    return f"""<div class="gap-summary">
  <div class="gap-stat"><span class="gap-k">評価済み回数</span><span class="gap-v">{n}回</span></div>
  <div class="gap-stat"><span class="gap-k">ストレート的中</span><span class="gap-v">{straight_hits}回</span><span class="gap-note">的中率{straight_hits / n * 100:.1f}%</span></div>
  <div class="gap-stat"><span class="gap-k">ボックス一致</span><span class="gap-v">{box_hits}回</span><span class="gap-note">一致率{box_hits / n * 100:.1f}%</span></div>
</div>"""


def row_html(rank: int, key: str, win_count: int, last_win_draw_no: int,
             last_win_date: str, draws_elapsed: int, max_elapsed: int,
             avg_interval: float, is_candidate: bool, verb: str = "当選") -> str:
    pct = max(3, round(draws_elapsed / max_elapsed * 100)) if max_elapsed > 0 else 3
    if is_candidate:
        badge = '<span class="badge badge-candidate">候補</span>'
        row_class = "row"
    else:
        remain = max(0, round(avg_interval - draws_elapsed))
        badge = f'<span class="badge badge-excluded">除外中・あと{remain}回</span>'
        row_class = "row row-excluded"
    return f"""<div class="{row_class}">
  <span class="rank">{rank:02d}</span>
  <span class="number">{key}</span>
  <div class="row-detail">
    <div class="row-stats"><b>{win_count}回</b>{verb}　最終 第{last_win_draw_no}回<small>（{format_date_ja(last_win_date)}）</small>　<small>平均間隔{avg_interval:.1f}回</small></div>
    <div class="meter">
      <div class="meter-track"><div class="meter-fill" style="width:{pct}%"></div></div>
      <span class="meter-value">{draws_elapsed}回経過</span>
    </div>
  </div>
  {badge}
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
            """SELECT draw_no, draw_date, number, prev_draw_no, prev_draw_date, gap
               FROM v_number_gaps ORDER BY draw_no DESC LIMIT ?""",
            (RECENT_N,),
        ).fetchall()

        candidates, excluded, _latest = get_candidates(conn, "straight", min_count=MIN_COUNT)
        digit_candidates, digit_excluded, _latest_digit = get_candidates(conn, "digit", min_count=MIN_COUNT)

        appeared = {r[0] for r in conn.execute("SELECT DISTINCT number FROM draws").fetchall()}
        zero_win_numbers = sorted(f"{i:03d}" for i in range(1000) if f"{i:03d}" not in appeared)
        one_win_rows = conn.execute(
            "SELECT number, last_win_draw_no, last_win_date FROM v_number_stats "
            "WHERE win_count = 1 ORDER BY number"
        ).fetchall()

        all_draws = conn.execute(
            "SELECT draw_no, draw_date, number FROM draws ORDER BY draw_no DESC"
        ).fetchall()

        pickup_matched, _pickup_digit_set = get_pickup_candidates(conn, min_count=MIN_COUNT, top=10)
        save_pickup(conn, pickup_matched, latest_draw_no)

        pickup_rows = conn.execute(
            """SELECT based_on_draw_no, target_draw_no, rank, picked_number, picked_box_key,
                      win_count, avg_interval, draws_elapsed,
                      target_draw_date, actual_number, actual_box_key, straight_hit, box_hit
               FROM v_pickup_results
               ORDER BY based_on_draw_no DESC, rank ASC"""
        ).fetchall()
    finally:
        conn.close()

    today_ja = format_date_ja(date.today().isoformat())

    chips = "\n".join(chip_html(*r) for r in recent)
    gap_summary = gap_summary_html(recent)

    candidate_keys = {e["key"] for e in candidates}
    all_entries = candidates + excluded
    elapsed_list = [e["draws_elapsed"] for e in all_entries]
    max_elapsed = max(elapsed_list) if elapsed_list else 1

    def build_rows(entries):
        visible, extra = [], []
        for rank, e in enumerate(entries, start=1):
            html = row_html(rank, e["key"], e["win_count"], e["last_win_draw_no"], e["last_win_date"],
                             e["draws_elapsed"], max_elapsed, e["avg_interval"], e["key"] in candidate_keys)
            (visible if rank <= TOP_VISIBLE else extra).append(html)
        return visible, extra

    top_sorted = sorted(all_entries, key=lambda e: (-e["win_count"], e["last_win_draw_no"]))[:TOP_EXPANDED]
    bottom_sorted = sorted(all_entries, key=lambda e: (e["win_count"], e["last_win_draw_no"]))[:TOP_EXPANDED]
    top_visible_rows, top_extra_rows = build_rows(top_sorted)
    bottom_visible_rows, bottom_extra_rows = build_rows(bottom_sorted)
    no_data_section = no_data_section_html(zero_win_numbers, one_win_rows)

    digit_candidate_keys = {e["key"] for e in digit_candidates}
    digit_entries = sorted(digit_candidates + digit_excluded, key=lambda e: -e["draws_elapsed"])
    digit_max_elapsed = max((e["draws_elapsed"] for e in digit_entries), default=1)
    digit_rows = "\n".join(
        row_html(rank, e["key"], e["win_count"], e["last_win_draw_no"], e["last_win_date"],
                 e["draws_elapsed"], digit_max_elapsed, e["avg_interval"],
                 e["key"] in digit_candidate_keys, verb="出現")
        for rank, e in enumerate(digit_entries, start=1)
    )

    history_rows = "\n".join(history_row_html(*r) for r in all_draws)

    pickup_groups = group_pickup_rows(pickup_rows)
    today_pickup_group = pickup_groups[0] if pickup_groups else None
    today_pickup_card = (today_pickup_table_html(today_pickup_group, max_date)
                         if today_pickup_group else "<p>ピックアップ対象がありません</p>")
    pickup_summary = pickup_summary_html(pickup_groups)
    pickup_history_visible = [pickup_card_html(g) for g in pickup_groups[1:1 + PICKUP_VISIBLE]]
    pickup_history_extra = [pickup_card_html(g) for g in pickup_groups[1 + PICKUP_VISIBLE:1 + PICKUP_EXPANDED]]

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
        <h2>今日のピックアップ数字</h2>
        <p>「ストレート当選傾向」の候補 × 「1桁の出現間隔」の候補（3桁すべて）を両方満たす番号。最大10個（満たない場合は少なくなる）</p>
      </div>
    </div>
    <div class="section-body">
      {today_pickup_card}
    </div>
  </section>

  <section class="section">
    <div class="section-head">
      <div>
        <h2>ピックアップ履行履歴</h2>
        <p>過去のピックアップと実際の当選数字の答え合わせ。対象回が未抽せんの場合は「結果待ち」</p>
      </div>
    </div>
    <div class="section-body">
      {pickup_summary}
      <div id="pickup-ledger">
{chr(10).join(pickup_history_visible) if pickup_history_visible else '<p>まだ履歴がありません</p>'}
        <div id="pickup-extra" class="is-hidden">
{chr(10).join(pickup_history_extra)}
        </div>
      </div>
    </div>
    <div class="btn-row">
      <button class="btn" onclick="toggleExtra('pickup-extra', this, 'もっと見る（上位{PICKUP_EXPANDED}件）', '閉じる')">もっと見る（上位{PICKUP_EXPANDED}件）</button>
    </div>
  </section>

  <section class="section">
    <div class="section-head">
      <div>
        <h2>直近{RECENT_N}回の当選数字</h2>
        <p>新しい回ほど左上・第{latest_draw_no}回から遡って{RECENT_N}回分</p>
      </div>
    </div>
    <div class="section-body">
      {gap_summary}
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
        <p>並び順まで一致／「候補」=最終当選から平均間隔以上経過、「除外中」=まだ平均間隔未達（候補{len(candidates)}件・除外{len(excluded)}件）</p>
      </div>
      <div class="section-head-actions">
        <button class="btn mode-btn is-active" onclick="setStraightMode('desc-top', this)">降順（上位{TOP_EXPANDED}）</button>
        <button class="btn mode-btn" onclick="setStraightMode('asc-top', this)">昇順（上位{TOP_EXPANDED}）</button>
        <button class="btn mode-btn" onclick="setStraightMode('asc-bottom', this)">昇順（全件の下から）</button>
        <button class="btn" onclick="toggleExcluded(['straight-ledger-top','straight-ledger-bottom'], this, '除外中を隠す', '除外中を表示')">除外中を隠す</button>
      </div>
    </div>
    <div id="straight-ledger-top" class="ledger" data-asc="false">
{chr(10).join(top_visible_rows)}
      <div id="straight-extra-top" class="is-hidden">
{chr(10).join(top_extra_rows)}
      </div>
    </div>
    <div id="straight-ledger-bottom" class="ledger is-hidden" data-asc="true">
{chr(10).join(bottom_visible_rows)}
      <div id="straight-extra-bottom" class="is-hidden">
{chr(10).join(bottom_extra_rows)}
      </div>
    </div>
    <div id="straight-more-top-row" class="btn-row">
      <button class="btn" onclick="toggleExtra('straight-extra-top', this, '上位{TOP_EXPANDED}まで見る', '閉じる')">上位{TOP_EXPANDED}まで見る</button>
    </div>
    <div id="straight-more-bottom-row" class="btn-row is-hidden">
      <button class="btn" onclick="toggleExtra('straight-extra-bottom', this, '下位{TOP_EXPANDED}まで見る', '閉じる')">下位{TOP_EXPANDED}まで見る</button>
    </div>
  </section>

  <section class="section">
    <div class="section-head">
      <div>
        <h2>1桁（0〜9）の出現間隔</h2>
        <p>並び順を問わず3桁のどこかにその数字が含まれていれば出現とみなす／最終出現から経過回数が多い順
        （候補{len(digit_candidates)}件・除外{len(digit_excluded)}件）
        参考: <a href="https://blog.umasaku.com/loto/numbers3-num-freq/" target="_blank" rel="noopener">umasaku.com</a></p>
      </div>
      <div class="section-head-actions">
        <button class="btn" onclick="toggleExcluded(['digit-ledger'], this, '除外中を隠す', '除外中を表示')">除外中を隠す</button>
      </div>
    </div>
    <div id="digit-ledger" class="ledger">
{digit_rows}
    </div>
  </section>

  {no_data_section}

  <footer class="note">
    <p>各回の抽せんは独立試行です。出現回数・経過回数・平均間隔・候補／除外の判定は過去{total}回の実績に生じた数字の偏り（サンプリング変動）の可視化であり、将来の当せんを予測するものではありません。ボックスは購入対象外のため非掲載（ストレート／セット購入向け）。1桁の出現間隔は位置（1桁目／2桁目／3桁目）を区別せずその数字が含まれていたかのみを見ている。</p>
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
