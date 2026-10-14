# numbers3-db

ナンバーズ3（予想・購入支援用）の当せんデータベース。

## 目的

過去の当せん番号を蓄積し、
- ストレート（並び順まで一致）の出現回数・最終当せん回・経過回数
- 直近の当せん数字・全履歴の参照

を把握する。約7000回規模の試行では数字の出現に偏り（サンプリング変動）が生じうるため、
その偏りの現状を可視化するためのツールであり、将来の当せんを予測するものではない。

購入対象はストレート／セットのみ（ボックス単体は購入しないためダッシュボードには非掲載）。

## 構成

```
numbers3-db/
├── schema.sql          # SQLiteスキーマ定義
├── db/numbers3.db       # 実データ（SQLite）
├── scripts/
│   ├── init_db.py        # schema.sql を適用してDBを初期化
│   ├── db_common.py       # DB接続・upsert共通ロジック
│   ├── import_csv.py      # CSVからの初回／追加取り込み
│   ├── scrape_update.py   # Web取得による更新（numbers-renban.tokyo、フォールバック用）
│   ├── update_data.py     # 自動更新の窓口（mk-mode CSV優先、失敗時scrape_update.pyへフォールバック）
│   ├── analyze.py         # 出現回数・経過回数のテキスト一覧（ターミナル確認用）
│   └── build_report.py    # ダッシュボードHTML（dashboard/report.html）を生成
├── dashboard/
│   ├── report.html         # build_report.py の生成物（Artifactとして公開するファイル）
│   └── ARTIFACT_URL.txt    # 公開済みArtifactのURL（再公開時はこのURLを指定して上書き更新）
└── data/                 # 取り込み用CSVの置き場
```

`/numbers3`（グローバルスラッシュコマンド、`~/.claude/commands/numbers3.md`）を実行すると
`update_data.py` → `build_report.py` → Artifact公開（既存URL更新）の順に自動実行される。
テキストでさっと確認したいだけの場合は `python3 scripts/analyze.py` を直接使う。

## データソースの選定理由

当初みずほ銀行公式サイトからの取得を試みたが、この実行環境からのアクセスは
Akamai WAFにより403 Forbiddenでブロックされた（curl・WebFetch双方で確認済み。
エラーページ上のAkamai `errors.edgesuite.net` の参照IDから断定）。

代替として `numbers-renban.tokyo`（ナンバーズ予想アプリ「RENBAN」が運営するデータ提供サイト）を採用。
- robots.txt で全面許可（`Disallow:` 空）
- 一覧ページ・詳細ページとも回号/日付/当選数字/口数/金額が構造化されたHTMLで取得可能
- 実データと公式の当せん金額が一致することを確認済み（第7091回で検証）

このサイトはみずほ公式ではないため、将来的にページ構造が変わると `scrape_update.py` の
パース処理が壊れる可能性がある点は留意する（CLAUDE.mdの方針どおり、取得失敗時はまず
自スクリプトのパースロジックを疑うこと）。

## スキーマ概要（schema.sql）

- `draws` テーブル: 1行=1回号。`draw_no` が主キー。
  - `number`: ストレート当せん番号（3桁文字列、ゼロ埋め）
  - `box_key`: `number` の桁を昇順ソートした文字列（ボックス集計のキー）。アプリ側で自動算出
  - `digit1`/`digit2`/`digit3`: 各桁（SQLite生成列・自動算出）
  - ストレート/ボックス/セットストレート/セットボックス/ミニそれぞれの口数・金額
  - `source`: `'csv_import'` または `'scrape'`（データの出所を追跡）
- `v_number_stats` ビュー: ストレート番号ごとの出現回数・最終当せん日・経過日数
- `v_box_stats` ビュー: ボックス番号（桁の組合せ）ごとの同上

## 使い方

### 初期化（初回のみ）
```bash
python3 scripts/init_db.py
```

### CSV取り込み
```bash
python3 scripts/import_csv.py data/<ファイル名>.csv
```
期待するヘッダー列や日付形式は `scripts/import_csv.py` 冒頭のコメントを参照。
列名の揺れ（「回号」「抽せん回」等）は自動吸収する。同じ回号が既にDBにある場合は上書き（upsert）。

### 自動更新（通常運用・これだけでOK）
```bash
python3 scripts/update_data.py
```
mk-mode.comのCSVを再DLして取り込む（ストレート/ボックス/セット/ミニ全て更新）。
取得失敗時は自動的にnumbers-renban.tokyoの差分スクレイピングにフォールバック（この場合box/set/miniは更新されない）。
`/numbers3` コマンドはこれを自動実行してから `analyze.py` を表示する。

### Web更新（numbers-renban.tokyoから直接・差分のみ）
```bash
python3 scripts/scrape_update.py
```
DB内の最大回号より新しい回のみ取得する（ストレートの口数・金額まで）。

### Web更新（初回構築・全件取得）
```bash
python3 scripts/scrape_update.py --full
```

### ボックス/セット/ミニの内訳を補完
一覧ページにはストレートの口数・金額しかないため、詳細ページを1回号ずつ個別取得する必要がある
（相手サイトへの配慮から1回号あたり約1秒の間隔を空けるため、全件だと数千回号分＝時間がかかる）。
```bash
python3 scripts/scrape_update.py --enrich               # box_countがNULLの行を全て補完
python3 scripts/scrape_update.py --enrich --limit 100    # 件数を絞って実行
```

### 分析（出現回数・経過回数の一覧）
```bash
python3 scripts/analyze.py                 # ストレート・ボックス両方、上位10件
python3 scripts/analyze.py --mode box --top 50 --min-count 3
```
出力例:
```
第1位: 当選数字「355」
  内訳：当選回数：18回、最終当選回：第6878回（2025年12月15日）、最終当選回から213回経過
```

## 現在のデータ状況（2026-10-14時点で実行・検証済み）

- **第1回（1994-10-07）〜第7091回（2026-10-13）の全7091回、欠番なし**で取得・取り込み完了
- ストレート/ボックス/セットストレート/セットボックス/ミニ、**全項目のNULLなし**（口数・金額とも）
- データソース: [mk-mode.com](https://www.mk-mode.com/rails/loto/numbers3) が公開する `NUMBERS3_ALL.csv`
  （`data/numbers3_mkmode_all.csv` に保存済み）を取り込み。`scrape_update.py --full` で得た
  numbers-renban.tokyo側のストレート結果と直近3回号分を突き合わせ、完全一致を確認済み（クロスバリデーション済み）
  - 同サイトの注記: 「一切保証はいたしません。正式なデータはみずほでご確認下さい」「古いデータで口数等が
    取得不能なものあり（＝0として記録されている可能性がある）」。1994年当時など古い回号の0は
    「本当に0」ではなく「データ欠落時のプレースホルダ」の可能性がある点に留意
- `mini_number`（ミニの当選2桁）はこのCSVには列が存在せず、現状は3回号分のみ
  `scrape_update.py --enrich` で個別取得済み（残りはNULL。全件欲しい場合は `--enrich` を実行）
- 運用: 今後は `python3 scripts/scrape_update.py` の定期実行で差分更新。
  mk-mode.comのCSVも定期的に再DLして `import_csv.py` にかければボックス/セット/ミニも自動更新される
  （COALESCEにより、新データがNULLの項目は既存値を上書きしない設計）
