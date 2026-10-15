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

-- 「今日のピックアップ数字」の履行履歴。predict.py --mode pickup / build_report.py 実行時に
-- 自動保存される。based_on_draw_no時点のデータで算出した予想＝次の回号(based_on_draw_no+1)が対象。
-- 同じbasedで再実行した場合は上書き（同一データからの再算出は結果が変わらないため）。
CREATE TABLE IF NOT EXISTS pickups (
    based_on_draw_no    INTEGER NOT NULL,  -- この回号までのデータに基づいて算出（予想対象は+1回）
    rank                INTEGER NOT NULL,  -- その回での順位（1〜10、当選回数が多い順）
    number              TEXT    NOT NULL CHECK (length(number) = 3),
    box_key             TEXT    NOT NULL CHECK (length(box_key) = 3),
    win_count           INTEGER,
    avg_interval        REAL,
    draws_elapsed       INTEGER,
    created_at          TEXT    NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (based_on_draw_no, rank)
);

-- ピックアップ結果の答え合わせ。対象回（based_on_draw_no+1）がまだ未抽せんの場合は
-- actual_number等がNULLになる（抽せん後、update_data.py実行で自動的に埋まる）。
DROP VIEW IF EXISTS v_pickup_results;
CREATE VIEW v_pickup_results AS
SELECT
    p.based_on_draw_no,
    p.based_on_draw_no + 1                         AS target_draw_no,
    p.rank,
    p.number                                       AS picked_number,
    p.box_key                                      AS picked_box_key,
    p.win_count, p.avg_interval, p.draws_elapsed,
    d.draw_date                                    AS target_draw_date,
    d.number                                       AS actual_number,
    d.box_key                                       AS actual_box_key,
    CASE WHEN d.number  IS NULL THEN NULL ELSE (p.number  = d.number)  END AS straight_hit,
    CASE WHEN d.box_key IS NULL THEN NULL ELSE (p.box_key = d.box_key) END AS box_hit
FROM pickups p
LEFT JOIN draws d ON d.draw_no = p.based_on_draw_no + 1;

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

-- 同じストレート番号が連続して当せんするまでの間隔（回号差）。1行=1回当せん、直前の当せん回号との差。
-- その番号の最初の当せんにはLAGが無いためprev_draw_no/gapはNULL（平均計算からは自動的に除外される）。
DROP VIEW IF EXISTS v_number_gaps;
CREATE VIEW v_number_gaps AS
SELECT
    number,
    draw_no,
    draw_date,
    LAG(draw_no)   OVER (PARTITION BY number ORDER BY draw_no) AS prev_draw_no,
    LAG(draw_date) OVER (PARTITION BY number ORDER BY draw_no) AS prev_draw_date,
    draw_no - LAG(draw_no) OVER (PARTITION BY number ORDER BY draw_no) AS gap
FROM draws;

-- ストレート番号ごとの平均当せん間隔（回数）。win_count>=2の番号のみavg_intervalが算出される
-- （1回しか出ていない番号は間隔のサンプルが無いためNULL＝算出不可）。
DROP VIEW IF EXISTS v_number_intervals;
CREATE VIEW v_number_intervals AS
SELECT
    s.number,
    s.win_count,
    s.last_win_date,
    s.last_win_draw_no,
    g.avg_interval
FROM v_number_stats s
LEFT JOIN (
    SELECT number, AVG(gap) AS avg_interval
    FROM v_number_gaps
    WHERE gap IS NOT NULL
    GROUP BY number
) g ON g.number = s.number;

-- ボックス番号版（同じ考え方をbox_keyに適用）
DROP VIEW IF EXISTS v_box_gaps;
CREATE VIEW v_box_gaps AS
SELECT
    box_key,
    draw_no,
    draw_no - LAG(draw_no) OVER (PARTITION BY box_key ORDER BY draw_no) AS gap
FROM draws;

DROP VIEW IF EXISTS v_box_intervals;
CREATE VIEW v_box_intervals AS
SELECT
    s.box_key,
    s.win_count,
    s.last_win_date,
    s.last_win_draw_no,
    g.avg_interval
FROM v_box_stats s
LEFT JOIN (
    SELECT box_key, AVG(gap) AS avg_interval
    FROM v_box_gaps
    WHERE gap IS NOT NULL
    GROUP BY box_key
) g ON g.box_key = s.box_key;

-- 1桁（0〜9）ごとの出現間隔分析。参考: https://blog.umasaku.com/loto/numbers3-num-freq/
-- 「どの桁（digit1/2/3のどの位置）で出たか」は区別せず、その数字が3桁のうちどこかに
-- 1回でも含まれていればその回で「出現した」とみなす（112なら「1」「2」が各1回出現）。
DROP VIEW IF EXISTS v_digit_appearances;
CREATE VIEW v_digit_appearances AS
SELECT d.digit AS digit, draws.draw_no AS draw_no, draws.draw_date AS draw_date
FROM draws, (
    SELECT 0 AS digit UNION SELECT 1 UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
    UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8 UNION SELECT 9
) d
WHERE draws.digit1 = d.digit OR draws.digit2 = d.digit OR draws.digit3 = d.digit;

-- 数字ごとの出現間隔（回号差）。1行=1回の出現、直前にその数字が出現した回号との差。
DROP VIEW IF EXISTS v_digit_gaps;
CREATE VIEW v_digit_gaps AS
SELECT
    digit,
    draw_no,
    draw_date,
    LAG(draw_no)   OVER (PARTITION BY digit ORDER BY draw_no) AS prev_draw_no,
    LAG(draw_date) OVER (PARTITION BY digit ORDER BY draw_no) AS prev_draw_date,
    draw_no - LAG(draw_no) OVER (PARTITION BY digit ORDER BY draw_no) AS gap
FROM v_digit_appearances;

-- 数字ごとの出現回数・最終出現・平均出現間隔。win_count列名はstraight/box版との構造統一のため
-- 流用しているが、ここでの意味は「出現回数」（当せんそのものではない）。
DROP VIEW IF EXISTS v_digit_stats;
CREATE VIEW v_digit_stats AS
SELECT
    digit,
    COUNT(*)           AS win_count,
    MAX(draw_date)      AS last_win_date,
    MAX(draw_no)         AS last_win_draw_no
FROM v_digit_appearances
GROUP BY digit;

DROP VIEW IF EXISTS v_digit_intervals;
CREATE VIEW v_digit_intervals AS
SELECT
    s.digit,
    s.win_count,
    s.last_win_date,
    s.last_win_draw_no,
    g.avg_interval
FROM v_digit_stats s
LEFT JOIN (
    SELECT digit, AVG(gap) AS avg_interval
    FROM v_digit_gaps
    WHERE gap IS NOT NULL
    GROUP BY digit
) g ON g.digit = s.digit;
