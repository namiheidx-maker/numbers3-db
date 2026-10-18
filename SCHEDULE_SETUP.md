# ナンバーズ3 データ更新スケジュール設定

## 概要

`scheduled_update.py` を使用して、曜日と時刻に応じた自動データ更新を実現します。

## 更新ルール

### 月～金（営業日）
- **09:00以降** — 最新のデータが取得できていなければ取得
- **18:00以降** — 当日のデータが取得できていなければ取得

### 土曜日
- **09:00以降** — 最新のデータ（金曜分）が取得できていなければ取得

### 日曜日
- **09:00以降** — 最新のデータが取得できていなければ取得

## Crontab 設定

### 設定手順

1. **crontab エディタを開く**
   ```bash
   crontab -e
   ```

2. **以下のエントリを追加**
   ```cron
   # 毎日 09:00 にチェック（月～日）
   0 9 * * * cd /Users/taikun/claude-projects/numbers3-db && python3 scripts/scheduled_update.py >> logs/update.log 2>&1
   
   # 平日 18:00 にチェック（月～金）
   0 18 * * 1-5 cd /Users/taikun/claude-projects/numbers3-db && python3 scripts/scheduled_update.py >> logs/update.log 2>&1
   ```

### crontab の曜日設定
- `1` = 月曜日
- `2` = 火曜日
- `3` = 水曜日
- `4` = 木曜日
- `5` = 金曜日
- `6` = 土曜日
- `0` = 日曜日（または `7`）
- `*` = 毎日

### ログ出力の確認

```bash
# ログディレクトリを作成（初回のみ）
mkdir -p logs

# ログを確認
tail -f logs/update.log
```

## 動作確認

### 手動実行（テスト）
```bash
cd /Users/taikun/claude-projects/numbers3-db
python3 scripts/scheduled_update.py
```

出力例：
```
[スキップ] 前営業日のデータ取得済み
[更新開始] 当日のデータを取得
[mk-mode CSV] 更新処理件数: 1
[完了]
```

### Crontab の確認
```bash
# 現在の crontab を表示
crontab -l

# crontab を削除（リセット）
crontab -r
```

## トラブルシューティング

### ログが出力されない
1. `logs/` ディレクトリが存在するか確認
2. パスが絶対パスになっているか確認
3. `crontab -l` で設定が正しいか確認

### 常に「スキップ」と表示される
1. データベースが正しく初期化されているか確認
2. 時刻設定が正しいか確認（朝9時以前で実行している可能性）
3. データベースのタイムゾーン設定を確認

### 権限エラーが発生する
```bash
# スクリプトに実行権限を付与
chmod +x scripts/scheduled_update.py
chmod +x scripts/update_data.py
```
