-- ナンバーズ3 当選データベース スキーマ
-- 単位: 金額は円、口数は件数

CREATE TABLE IF NOT EXISTS draws (
    draw_no             INTEGER PRIMARY KEY,   -- 回号（第n回）
    draw_date           TEXT    NOT NULL,       -- 抽せん日 YYYY-MM-DD
    number              TEXT    NOT NULL CHECK (length(number) = 3 AND number GLOB '[0-9][0-9][0-9]'),
    box_key             TEXT    NOT NULL CHECK (length(box_key) = 3),  -- numberの桁を昇順ソートした文字列（ボックス集計用）

    -- 各桁（ストレート内の位置別分析用）。SQLiteの生成列で自動算出するため書き込み時のバグが入らない
    digit1              INTEGER GENERATED ALWAYS AS (CAST(substr(number, 1, 1) AS INTEGER)) STORED,
    digit2              INTEGER GENERATED ALWAYS AS (CAST(substr(number, 2, 1) AS INTEGER)) STORED,
    digit3              INTEGER GENERATED ALWAYS AS (CAST(substr(number, 3, 1) AS INTEGER)) STORED,

    straight_count      INTEGER,  -- ストレート 口数
    straight_amount     INTEGER,  -- ストレート 当せん金額（円）
    box_count           INTEGER,  -- ボックス 口数
    box_amount          INTEGER,  -- ボックス 当せん金額（円）
    set_straight_count  INTEGER,  -- セット(ストレート) 口数
    set_straight_amount INTEGER,  -- セット(ストレート) 当せん金額（円）
    set_box_count       INTEGER,  -- セット(ボックス) 口数
    set_box_amount      INTEGER,  -- セット(ボックス) 当せん金額（円）
    mini_number         TEXT,     -- ナンバーズ3ミニ 当せん番号（下2桁、2桁ゼロ埋め）
    mini_count          INTEGER,  -- ミニ 口数
    mini_amount         INTEGER,  -- ミニ 当せん金額（円）

    source              TEXT    NOT NULL DEFAULT 'unknown',  -- 'csv_import' | 'scrape'
    created_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_draws_number   ON draws (number);
CREATE INDEX IF NOT EXISTS idx_draws_box_key  ON draws (box_key);
CREATE INDEX IF NOT EXISTS idx_draws_date     ON draws (draw_date);

-- updated_at を書き込み時刻に自動更新
CREATE TRIGGER IF NOT EXISTS trg_draws_updated_at
AFTER UPDATE ON draws
FOR EACH ROW
BEGIN
    UPDATE draws SET updated_at = datetime('now', 'localtime') WHERE draw_no = NEW.draw_no;
END;

-- ストレート番号（000〜999）ごとの出現統計
-- win_count: 出現回数 / last_win_date, last_win_draw_no: 最後に当せんした日・回号
-- days_since_last_win: 最後の当せんからの経過日数（今日基準）
DROP VIEW IF EXISTS v_number_stats;
CREATE VIEW v_number_stats AS
SELECT
    number,
    COUNT(*)                                            AS win_count,
    MAX(draw_date)                                      AS last_win_date,
    MAX(draw_no)                                        AS last_win_draw_no,
    CAST(julianday('now', 'localtime') - julianday(MAX(draw_date)) AS INTEGER) AS days_since_last_win
FROM draws
GROUP BY number;

-- ボックス番号（桁の組み合わせ、順不同）ごとの出現統計
DROP VIEW IF EXISTS v_box_stats;
CREATE VIEW v_box_stats AS
SELECT
    box_key,
    COUNT(*)                                            AS win_count,
    MAX(draw_date)                                      AS last_win_date,
    MAX(draw_no)                                        AS last_win_draw_no,
    CAST(julianday('now', 'localtime') - julianday(MAX(draw_date)) AS INTEGER) AS days_since_last_win
FROM draws
GROUP BY box_key;
