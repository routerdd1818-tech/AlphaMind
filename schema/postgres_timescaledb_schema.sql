-- ==============================================================================
-- AlphaMind AI — Polyglot Persistence Architecture
-- Layer 1: PostgreSQL 16 + TimescaleDB + pgvector
-- Standards: Strict financial precision, auditable timestamps, optimized indexing
-- ==============================================================================

-- 0. Required Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "timescaledb" CASCADE;
CREATE EXTENSION IF NOT EXISTS "vector";

-- ------------------------------------------------------------------------------
-- 1. Relational Core: Companies & Sector Metadata
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    stock_symbol VARCHAR(16) PRIMARY KEY,          -- e.g. '2330.TW', 'NVDA'
    name VARCHAR(64) NOT NULL,                    -- e.g. '台積電', 'NVIDIA'
    market VARCHAR(16) NOT NULL,                  -- 'TWSE', 'TPEx', 'NYSE', 'NASDAQ', 'TSE', 'KRX', 'HKEX', 'EURONEXT'
    region VARCHAR(8) NOT NULL,                   -- 'TW', 'US', 'JP', 'KR', 'HK', 'EU'
    currency VARCHAR(3) NOT NULL DEFAULT 'TWD',   -- 'TWD', 'USD', 'JPY', 'KRW', 'HKD', 'EUR'
    shares_outstanding BIGINT,                    -- 流通股數
    industry_category VARCHAR(32) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS concept_sectors (
    sector_id VARCHAR(64) PRIMARY KEY,            -- e.g. 'CoWoS', 'Liquid_Cooling', 'Silicon_Photonics'
    name VARCHAR(64) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Company to Multi-label Sector Mapping
CREATE TABLE IF NOT EXISTS company_sector_tags (
    stock_symbol VARCHAR(16) NOT NULL REFERENCES companies(stock_symbol) ON DELETE CASCADE,
    sector_id VARCHAR(64) NOT NULL REFERENCES concept_sectors(sector_id) ON DELETE CASCADE,
    weight NUMERIC(4, 3) NOT NULL DEFAULT 1.000, -- 權重 0.000 ~ 1.000
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (stock_symbol, sector_id)
);

-- ------------------------------------------------------------------------------
-- 2. Time-Series Layer: Market Ticks & OHLCV Hypertables (TimescaleDB)
-- ------------------------------------------------------------------------------

-- High-Frequency Ticks (Tick 級別逐筆成交)
CREATE TABLE IF NOT EXISTS market_ticks (
    time TIMESTAMPTZ NOT NULL,
    stock_symbol VARCHAR(16) NOT NULL,
    price NUMERIC(14, 4) NOT NULL,
    volume INT NOT NULL,
    turnover NUMERIC(18, 2) NOT NULL,
    bid_ask_flag SMALLINT NOT NULL,              -- 1: 外盤買進, -1: 內盤賣出, 0: 無方向
    is_large_order BOOLEAN NOT NULL DEFAULT false, -- 單筆成交金額 > 門檻
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('market_ticks', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS idx_market_ticks_symbol_time ON market_ticks (stock_symbol, time DESC);

-- 1-Minute OHLCV (1 分鐘 K 線，含主動買賣盤與 VWAP)
CREATE TABLE IF NOT EXISTS market_ohlcv_1m (
    time TIMESTAMPTZ NOT NULL,
    stock_symbol VARCHAR(16) NOT NULL,
    open NUMERIC(14, 4) NOT NULL,
    high NUMERIC(14, 4) NOT NULL,
    low NUMERIC(14, 4) NOT NULL,
    close NUMERIC(14, 4) NOT NULL,
    vwap NUMERIC(14, 4) NOT NULL,
    volume BIGINT NOT NULL,
    turnover NUMERIC(18, 2) NOT NULL,
    buy_volume BIGINT NOT NULL DEFAULT 0,
    sell_volume BIGINT NOT NULL DEFAULT 0,
    large_order_net_volume BIGINT NOT NULL DEFAULT 0
);

SELECT create_hypertable('market_ohlcv_1m', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');
CREATE UNIQUE INDEX IF NOT EXISTS idx_ohlcv_1m_unique ON market_ohlcv_1m (stock_symbol, time DESC);

-- Daily OHLCV & Institutional Institutional Flows (日 K 與籌碼面)
CREATE TABLE IF NOT EXISTS market_ohlcv_1d (
    time TIMESTAMPTZ NOT NULL,
    stock_symbol VARCHAR(16) NOT NULL,
    open NUMERIC(14, 4) NOT NULL,
    high NUMERIC(14, 4) NOT NULL,
    low NUMERIC(14, 4) NOT NULL,
    close NUMERIC(14, 4) NOT NULL,
    volume BIGINT NOT NULL,
    turnover NUMERIC(18, 2) NOT NULL,
    foreign_buy_net BIGINT NOT NULL DEFAULT 0,
    investment_trust_buy_net BIGINT NOT NULL DEFAULT 0,
    dealer_buy_net BIGINT NOT NULL DEFAULT 0,
    margin_balance BIGINT NOT NULL DEFAULT 0,
    short_balance BIGINT NOT NULL DEFAULT 0,
    major_holders_ratio NUMERIC(5, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('market_ohlcv_1d', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 month');
CREATE UNIQUE INDEX IF NOT EXISTS idx_ohlcv_1d_unique ON market_ohlcv_1d (stock_symbol, time DESC);

-- ------------------------------------------------------------------------------
-- 3. Sector Flow Engine: Money Flow Ratio Snapshots
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sector_money_flow_snapshot (
    time TIMESTAMPTZ NOT NULL,
    sector_id VARCHAR(64) NOT NULL,
    turnover NUMERIC(18, 2) NOT NULL,
    market_turnover NUMERIC(18, 2) NOT NULL,
    turnover_ratio NUMERIC(8, 4) NOT NULL,
    delta_turnover_ratio_5m NUMERIC(8, 4),
    delta_turnover_ratio_15m NUMERIC(8, 4),
    delta_turnover_ratio_60m NUMERIC(8, 4),
    market_cap_ratio NUMERIC(8, 4) NOT NULL,
    flow_ratio NUMERIC(8, 4) NOT NULL,
    leading_stock_symbol VARCHAR(16),
    net_large_order_inflow NUMERIC(18, 2)
);

SELECT create_hypertable('sector_money_flow_snapshot', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');
CREATE INDEX IF NOT EXISTS idx_sector_flow_time ON sector_money_flow_snapshot (sector_id, time DESC);

-- ------------------------------------------------------------------------------
-- 4. Global Macro, Rates, FX & Sentiment (美、台、日、韓、港、歐)
-- ------------------------------------------------------------------------------

-- 總經與經濟景氣指標 (CPI, PPI, PMI, GDP, 失業率)
CREATE TABLE IF NOT EXISTS macro_economic_metrics (
    time TIMESTAMPTZ NOT NULL,
    region VARCHAR(8) NOT NULL,                  -- 'US', 'TW', 'JP', 'KR', 'HK', 'EU'
    metric_name VARCHAR(32) NOT NULL,            -- 'CPI_YOY', 'CORE_CPI', 'MANUFACTURING_PMI', 'GDP_GROWTH', 'UNEMPLOYMENT_RATE'
    value NUMERIC(12, 4) NOT NULL,
    consensus_value NUMERIC(12, 4),              -- 市場預期值
    previous_value NUMERIC(12, 4),               -- 前值
    surprise_pct NUMERIC(8, 4),                  -- 超預期幅度 (%)
    source VARCHAR(32) NOT NULL,                 -- 'FRED', 'BLS', 'DGBAS', 'BOJ', 'BOK', 'EUROSTAT'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('macro_economic_metrics', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 year');
CREATE INDEX IF NOT EXISTS idx_macro_metrics_lookup ON macro_economic_metrics (region, metric_name, time DESC);

-- 利率與匯率表 (政策利率、2Y/10Y 公債殖利率、利差曲線、主要匯率)
CREATE TABLE IF NOT EXISTS macro_rates_fx (
    time TIMESTAMPTZ NOT NULL,
    region VARCHAR(8) NOT NULL,                  -- 'US', 'TW', 'JP', 'KR', 'HK', 'EU'
    central_bank_policy_rate NUMERIC(8, 4) NOT NULL, -- 央行基準利率 (%)
    yield_2y NUMERIC(8, 4),                      -- 2年期公債殖利率 (%)
    yield_10y NUMERIC(8, 4),                     -- 10年期公債殖利率 (%)
    yield_spread_10y_2y NUMERIC(8, 4),           -- 10Y - 2Y 利差 (倒掛指標)
    fx_to_usd NUMERIC(12, 4) NOT NULL,           -- 對美元匯率 (USD/TWD, USD/JPY, USD/KRW, USD/HKD, EUR/USD)
    fx_change_pct_1d NUMERIC(8, 4),              -- 匯率單日漲跌幅 (%)
    dxy_index NUMERIC(8, 4),                     -- 美元指數 (全球通用參考)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

SELECT create_hypertable('macro_rates_fx', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 month');
CREATE INDEX IF NOT EXISTS idx_macro_rates_fx_lookup ON macro_rates_fx (region, time DESC);

-- 央行利率預測與期貨降息機率矩陣 (FedWatch, ECB OIS, BOJ 升息隱含機率)
CREATE TABLE IF NOT EXISTS rate_cut_expectations (
    time TIMESTAMPTZ NOT NULL,
    region VARCHAR(8) NOT NULL,                  -- 'US', 'EU', 'JP', 'TW', 'KR'
    target_meeting_date DATE NOT NULL,           -- 下次/指定 FOMC / ECB / CBC 會議日期
    current_target_rate_range VARCHAR(32) NOT NULL, -- 如 '5.25%-5.50%'
    prob_cut_25bp NUMERIC(6, 3) NOT NULL,        -- 降息 1 碼機率 (0.000 ~ 1.000)
    prob_cut_50bp NUMERIC(6, 3) NOT NULL,        -- 降息 2 碼機率
    prob_hold NUMERIC(6, 3) NOT NULL,            -- 維持不變機率
    prob_hike_25bp NUMERIC(6, 3) NOT NULL,       -- 升息 1 碼機率
    implied_terminal_rate NUMERIC(8, 4),         -- 隱含終點利率
    source VARCHAR(32) NOT NULL DEFAULT 'CME_FEDWATCH'
);

SELECT create_hypertable('rate_cut_expectations', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 month');
CREATE INDEX IF NOT EXISTS idx_rate_cut_expectations ON rate_cut_expectations (region, target_meeting_date, time DESC);

-- 各區域市場波動率與情緒指數 (VIX, VSTOXX, VNKY, VKOSPI, 融資維持率)
CREATE TABLE IF NOT EXISTS market_volatility_sentiment (
    time TIMESTAMPTZ NOT NULL,
    region VARCHAR(8) NOT NULL,                  -- 'US', 'TW', 'JP', 'KR', 'HK', 'EU'
    volatility_index_value NUMERIC(8, 4) NOT NULL, -- 美: VIX, 歐: VSTOXX, 日: VNKY, 韓: VKOSPI, 台: TAIWAVIX, 港: VHSI
    volatility_term_structure_ratio NUMERIC(8, 4), -- 波動率期限結構比值 (VIX9D / VIX，大於1表示極度恐慌)
    put_call_ratio NUMERIC(8, 4),                -- 選擇權 Put/Call Ratio
    fear_greed_score NUMERIC(5, 2),              -- 恐懼貪婪指數 (0~100)
    margin_maintenance_ratio NUMERIC(6, 2),      -- 信用交易融資維持率 (台股 >160%安全，<130%斷頭)
    foreign_liquidity_bias VARCHAR(16)           -- 'STRONG_INFLOW', 'NEUTRAL', 'FLIGHT_TO_SAFETY'
);

SELECT create_hypertable('market_volatility_sentiment', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '1 month');
CREATE INDEX IF NOT EXISTS idx_volatility_sentiment ON market_volatility_sentiment (region, time DESC);

-- ------------------------------------------------------------------------------
-- 5. Fundamental Health & Target/Stop-Loss Levels
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS financial_reports (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol VARCHAR(16) NOT NULL REFERENCES companies(stock_symbol) ON DELETE CASCADE,
    year SMALLINT NOT NULL,
    quarter SMALLINT NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    revenue NUMERIC(18, 2) NOT NULL,
    gross_profit NUMERIC(18, 2) NOT NULL,
    operating_income NUMERIC(18, 2) NOT NULL,
    net_income NUMERIC(18, 2) NOT NULL,
    eps NUMERIC(10, 4) NOT NULL,
    operating_cash_flow NUMERIC(18, 2),
    free_cash_flow NUMERIC(18, 2),
    gross_margin NUMERIC(8, 4) NOT NULL,
    operating_margin NUMERIC(8, 4) NOT NULL,
    net_margin NUMERIC(8, 4) NOT NULL,
    gross_margin_qoq_slope NUMERIC(8, 4),
    operating_margin_qoq_slope NUMERIC(8, 4),
    piotroski_f_score SMALLINT CHECK (piotroski_f_score BETWEEN 0 AND 9),
    altman_z_score NUMERIC(8, 4),
    raw_statement_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_company_report_period UNIQUE (stock_symbol, year, quarter)
);

CREATE TABLE IF NOT EXISTS price_target_stop_levels (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol VARCHAR(16) NOT NULL REFERENCES companies(stock_symbol) ON DELETE CASCADE,
    as_of_date DATE NOT NULL,
    target_price_conservative NUMERIC(14, 4),
    target_price_consensus NUMERIC(14, 4),
    target_price_optimistic NUMERIC(14, 4),
    forward_return_20d_pred NUMERIC(8, 4),
    atr_14 NUMERIC(14, 4) NOT NULL,
    dynamic_stop_loss_price NUMERIC(14, 4) NOT NULL,
    institutional_vwap_20d NUMERIC(14, 4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_company_levels_date UNIQUE (stock_symbol, as_of_date)
);

-- ------------------------------------------------------------------------------
-- 6. NLP News Extraction & Vector Search (pgvector)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_features (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(32) NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    url TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    sentiment_score NUMERIC(4, 3) NOT NULL CHECK (sentiment_score BETWEEN -1.000 AND 1.000),
    event_category VARCHAR(32) NOT NULL,
    impact_horizon VARCHAR(16) NOT NULL CHECK (impact_horizon IN ('SHORT_TERM', 'LONG_TERM')),
    mentioned_symbols VARCHAR(16)[] NOT NULL,
    affected_graph_nodes VARCHAR(64)[] NOT NULL,
    embedding vector(1536),
    raw_metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_published_at ON news_features (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_symbols_gin ON news_features USING GIN (mentioned_symbols);
CREATE INDEX IF NOT EXISTS idx_news_embedding_hnsw ON news_features USING hnsw (embedding vector_cosine_ops);

-- ------------------------------------------------------------------------------
-- 7. Strategy Configuration & Backtest Execution Logs
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS strategies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(64) NOT NULL,
    type VARCHAR(32) NOT NULL,
    parameters JSONB NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital NUMERIC(18, 2) NOT NULL,
    final_equity NUMERIC(18, 2) NOT NULL,
    cagr NUMERIC(8, 4) NOT NULL,
    max_drawdown NUMERIC(8, 4) NOT NULL,
    sharpe_ratio NUMERIC(8, 4) NOT NULL,
    win_rate NUMERIC(8, 4) NOT NULL,
    profit_factor NUMERIC(8, 4),
    trades_count INT NOT NULL,
    equity_curve JSONB NOT NULL,
    trade_logs JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
