-- ==============================================================================
-- AlphaMind AI — Supabase All-in-One Production Schema
-- Designed specifically for Supabase:
-- 1. 100% Native PostgreSQL Partitioning (Replaces TimescaleDB dependency)
-- 2. Recursive CTE Graph Traversal (Replaces Neo4j dependency)
-- 3. pgvector support for News Feature Embedding
-- 4. Row Level Security (RLS) & Performance Indexes
-- ==============================================================================

-- 0. Required Supabase Extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ------------------------------------------------------------------------------
-- 1. Core Reference Tables: Companies & Dynamic Sector Multi-Labels
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    stock_symbol VARCHAR(16) PRIMARY KEY,          -- e.g. '2330.TW', 'NVDA'
    name VARCHAR(64) NOT NULL,                    -- e.g. '台積電', 'NVIDIA'
    market VARCHAR(16) NOT NULL,                  -- 'TWSE', 'TPEx', 'NYSE', 'NASDAQ'
    region VARCHAR(8) NOT NULL DEFAULT 'TW',      -- 'TW', 'US', 'JP', 'KR', 'HK', 'EU'
    currency VARCHAR(3) NOT NULL DEFAULT 'TWD',
    shares_outstanding BIGINT,
    industry_category VARCHAR(32) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS concept_sectors (
    sector_id VARCHAR(64) PRIMARY KEY,            -- e.g. 'CoWoS', 'Cooling', 'CPO'
    name VARCHAR(64) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS company_sector_tags (
    stock_symbol VARCHAR(16) NOT NULL REFERENCES companies(stock_symbol) ON DELETE CASCADE,
    sector_id VARCHAR(64) NOT NULL REFERENCES concept_sectors(sector_id) ON DELETE CASCADE,
    weight NUMERIC(4, 3) NOT NULL DEFAULT 1.000, -- 題材純度權重 0.000 ~ 1.000
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (stock_symbol, sector_id)
);

-- ------------------------------------------------------------------------------
-- 2. Neo4j Replacement: Supply Chain Graph Table & Recursive Traversal Function
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS supply_chain_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    leader_symbol VARCHAR(16) NOT NULL REFERENCES companies(stock_symbol) ON DELETE CASCADE,
    supplier_symbol VARCHAR(16) NOT NULL REFERENCES companies(stock_symbol) ON DELETE CASCADE,
    relationship_type VARCHAR(32) NOT NULL DEFAULT 'SUPPLIES_TO',
    product_category VARCHAR(64) NOT NULL,
    revenue_share NUMERIC(5, 4) NOT NULL DEFAULT 0.1000,   -- 供貨營收佔比 0.0000 ~ 1.0000
    is_sole_supplier BOOLEAN NOT NULL DEFAULT false,       -- 是否為獨家供應商
    substitutability_score NUMERIC(5, 4) NOT NULL DEFAULT 0.5000, -- 替代難度 (0.0 極易 ~ 1.0 不可替代)
    confidence NUMERIC(5, 4) NOT NULL DEFAULT 0.9000,      -- 置信度
    pricing_power_summary TEXT,                            -- 議價權評述
    source_doc TEXT,                                       -- 年報或法說會來源
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_supply_chain_edge UNIQUE (leader_symbol, supplier_symbol, product_category)
);

CREATE INDEX IF NOT EXISTS idx_sc_leader ON supply_chain_relationships(leader_symbol);
CREATE INDEX IF NOT EXISTS idx_sc_supplier ON supply_chain_relationships(supplier_symbol);

-- Supabase RPC 函數：遞迴遍歷 1 至 N 階供應鏈，計算累計營收權重與替代性
CREATE OR REPLACE FUNCTION get_supply_chain_network(
    p_root_symbol VARCHAR(16),
    p_max_depth INT DEFAULT 3
)
RETURNS TABLE (
    tier INT,
    leader_symbol VARCHAR(16),
    supplier_symbol VARCHAR(16),
    supplier_name VARCHAR(64),
    product_category VARCHAR(64),
    revenue_share NUMERIC,
    is_sole_supplier BOOLEAN,
    substitutability_score NUMERIC,
    cumulative_weight NUMERIC,
    chain_path TEXT[]
) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE sc_cte AS (
        -- Base Case: 1 階直屬供應商
        SELECT 
            1 AS tier,
            r.leader_symbol,
            r.supplier_symbol,
            c.name AS supplier_name,
            r.product_category,
            r.revenue_share,
            r.is_sole_supplier,
            r.substitutability_score,
            r.revenue_share AS cumulative_weight,
            ARRAY[r.leader_symbol::TEXT, r.supplier_symbol::TEXT] AS chain_path
        FROM supply_chain_relationships r
        JOIN companies c ON c.stock_symbol = r.supplier_symbol
        WHERE r.leader_symbol = p_root_symbol

        UNION ALL

        -- Recursive Step: 2 至 N 階擴展
        SELECT 
            parent.tier + 1,
            child.leader_symbol,
            child.supplier_symbol,
            c.name AS supplier_name,
            child.product_category,
            child.revenue_share,
            child.is_sole_supplier,
            child.substitutability_score,
            (parent.cumulative_weight * child.revenue_share) AS cumulative_weight,
            parent.chain_path || child.supplier_symbol::TEXT AS chain_path
        FROM sc_cte parent
        JOIN supply_chain_relationships child ON child.leader_symbol = parent.supplier_symbol
        JOIN companies c ON c.stock_symbol = child.supplier_symbol
        WHERE parent.tier < p_max_depth
          AND NOT (child.supplier_symbol::TEXT = ANY(parent.chain_path)) -- 防止環狀循環
    )
    SELECT * FROM sc_cte ORDER BY tier ASC, cumulative_weight DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ------------------------------------------------------------------------------
-- 3. TimescaleDB Replacement: Native PostgreSQL Partitioned Tables
-- ------------------------------------------------------------------------------

-- Daily OHLCV & Institutional Flows (分區表)
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
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (time, stock_symbol)
) PARTITION BY RANGE (time);

-- 預先建立 2025、2026、2027 年分區
CREATE TABLE IF NOT EXISTS market_ohlcv_1d_y2025 PARTITION OF market_ohlcv_1d
    FOR VALUES FROM ('2025-01-01 00:00:00+00') TO ('2026-01-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS market_ohlcv_1d_y2026 PARTITION OF market_ohlcv_1d
    FOR VALUES FROM ('2026-01-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');

CREATE TABLE IF NOT EXISTS market_ohlcv_1d_y2027 PARTITION OF market_ohlcv_1d
    FOR VALUES FROM ('2027-01-01 00:00:00+00') TO ('2028-01-01 00:00:00+00');

CREATE INDEX IF NOT EXISTS idx_ohlcv_1d_symbol_time ON market_ohlcv_1d(stock_symbol, time DESC);

-- 族群資金流向快照 (分區表)
CREATE TABLE IF NOT EXISTS sector_money_flow_snapshot (
    time TIMESTAMPTZ NOT NULL,
    sector_id VARCHAR(64) NOT NULL,
    turnover NUMERIC(18, 2) NOT NULL,
    market_turnover NUMERIC(18, 2) NOT NULL,
    turnover_ratio NUMERIC(8, 4) NOT NULL,
    delta_turnover_ratio_5m NUMERIC(8, 4),
    delta_turnover_ratio_15m NUMERIC(8, 4),
    market_cap_ratio NUMERIC(8, 4) NOT NULL,
    flow_ratio NUMERIC(8, 4) NOT NULL,
    leading_stock_symbol VARCHAR(16),
    PRIMARY KEY (time, sector_id)
) PARTITION BY RANGE (time);

CREATE TABLE IF NOT EXISTS sector_flow_y2026 PARTITION OF sector_money_flow_snapshot
    FOR VALUES FROM ('2026-01-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');

CREATE INDEX IF NOT EXISTS idx_sector_flow_lookup ON sector_money_flow_snapshot(sector_id, time DESC);

-- 6 國總經、利率、匯率表 (分區表)
CREATE TABLE IF NOT EXISTS macro_rates_fx (
    time TIMESTAMPTZ NOT NULL,
    region VARCHAR(8) NOT NULL,                  -- 'US', 'TW', 'JP', 'KR', 'HK', 'EU'
    central_bank_policy_rate NUMERIC(8, 4) NOT NULL,
    yield_2y NUMERIC(8, 4),
    yield_10y NUMERIC(8, 4),
    yield_spread_10y_2y NUMERIC(8, 4),
    fx_to_usd NUMERIC(12, 4) NOT NULL,
    fx_change_pct_1d NUMERIC(8, 4),
    dxy_index NUMERIC(8, 4),
    PRIMARY KEY (time, region)
) PARTITION BY RANGE (time);

CREATE TABLE IF NOT EXISTS macro_rates_fx_y2026 PARTITION OF macro_rates_fx
    FOR VALUES FROM ('2026-01-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');

CREATE INDEX IF NOT EXISTS idx_macro_rates_lookup ON macro_rates_fx(region, time DESC);

-- ------------------------------------------------------------------------------
-- 4. Fundamental Health & Dual-Track Stops
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS financial_reports (
    id BIGSERIAL PRIMARY KEY,
    stock_symbol VARCHAR(16) NOT NULL REFERENCES companies(stock_symbol) ON DELETE CASCADE,
    year SMALLINT NOT NULL,
    quarter SMALLINT NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    revenue NUMERIC(18, 2) NOT NULL,
    net_income NUMERIC(18, 2) NOT NULL,
    operating_cash_flow NUMERIC(18, 2),
    gross_margin NUMERIC(8, 4) NOT NULL,
    operating_margin NUMERIC(8, 4) NOT NULL,
    piotroski_f_score SMALLINT CHECK (piotroski_f_score BETWEEN 0 AND 9),
    altman_z_score NUMERIC(8, 4),
    raw_statement_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_supabase_report_period UNIQUE (stock_symbol, year, quarter)
);

CREATE TABLE IF NOT EXISTS dual_stop_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stock_symbol VARCHAR(16) NOT NULL REFERENCES companies(stock_symbol) ON DELETE CASCADE,
    as_of_date DATE NOT NULL,
    -- 現價預測 (未持倉)
    current_market_price NUMERIC(14, 4) NOT NULL,
    entry_zone_low NUMERIC(14, 4) NOT NULL,
    entry_zone_high NUMERIC(14, 4) NOT NULL,
    initial_stop_price NUMERIC(14, 4) NOT NULL,
    consensus_target_price NUMERIC(14, 4) NOT NULL,
    risk_reward_ratio NUMERIC(6, 2) NOT NULL,
    is_favorable_entry BOOLEAN NOT NULL,
    -- 持倉策略參考 (以建議均價)
    sample_cost_price NUMERIC(14, 4),
    break_even_stop_price NUMERIC(14, 4),
    effective_trailing_stop NUMERIC(14, 4),
    tier_1_take_profit NUMERIC(14, 4),
    tier_2_take_profit NUMERIC(14, 4),
    action_recommendation VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_dual_stops_symbol_date UNIQUE (stock_symbol, as_of_date)
);

-- ------------------------------------------------------------------------------
-- 5. AI News & Embedding (pgvector)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_features (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(32) NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    sentiment_score NUMERIC(4, 3) NOT NULL,
    event_category VARCHAR(32) NOT NULL,
    impact_horizon VARCHAR(16) NOT NULL,
    mentioned_symbols VARCHAR(16)[] NOT NULL,
    affected_nodes VARCHAR(64)[] NOT NULL,
    embedding vector(1536),                      -- 支援 pgvector 語意比對
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_news_features_pub ON news_features(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_embedding_hnsw ON news_features USING hnsw (embedding vector_cosine_ops);

-- ------------------------------------------------------------------------------
-- 6. Initial Seed Data (台積電 2330、弘塑 3131、奇鋐 3017、NVIDIA)
-- ------------------------------------------------------------------------------
INSERT INTO companies (stock_symbol, name, market, region, currency, industry_category)
VALUES 
    ('2330.TW', '台積電', 'TWSE', 'TW', 'TWD', '半導體'),
    ('3131.TW', '弘塑科技', 'TPEx', 'TW', 'TWD', '半導體設備'),
    ('3017.TW', '奇鋐科技', 'TWSE', 'TW', 'TWD', '電腦及週邊'),
    ('NVDA', 'NVIDIA', 'NASDAQ', 'US', 'USD', 'AI晶片')
ON CONFLICT (stock_symbol) DO NOTHING;

INSERT INTO concept_sectors (sector_id, name, description)
VALUES
    ('CoWoS', 'CoWoS 先進封裝', '先進晶圓級與基板級封裝'),
    ('Cooling', '水冷與散熱技術', '伺服器液冷板與水冷散熱模組')
ON CONFLICT (sector_id) DO NOTHING;

INSERT INTO supply_chain_relationships 
    (leader_symbol, supplier_symbol, relationship_type, product_category, revenue_share, is_sole_supplier, substitutability_score, confidence, pricing_power_summary)
VALUES
    ('NVDA', '2330.TW', 'SUPPLIES_TO', '4N/3nm 晶圓代工與 CoWoS 封裝', 0.1500, true, 0.9800, 0.9900, 'AI 旗艦晶片唯一量產廠，具備全面定價權'),
    ('2330.TW', '3131.TW', 'SUPPLIES_TO', 'CoWoS 濕製程單晶圓清洗設備', 0.3800, false, 0.8500, 0.9500, '先進封裝擴產關鍵機台，獲驗證通過，轉嫁能力強')
ON CONFLICT (leader_symbol, supplier_symbol, product_category) DO NOTHING;

-- ------------------------------------------------------------------------------
-- 7. Taiwan ETF Zone Tables (ETF 基本資料、各期報酬率、成分股權重明細)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS etf_profiles (
    etf_symbol VARCHAR(16) PRIMARY KEY,            -- e.g. '0050', '00878', '00919'
    etf_name VARCHAR(64) NOT NULL,
    category VARCHAR(32) NOT NULL,                 -- '市值型', '高股息', '科技與半導體', '債券型', '海外與槓桿'
    issuer VARCHAR(32) NOT NULL,
    price NUMERIC(14, 4) NOT NULL,
    nav NUMERIC(14, 4),
    premium_discount_pct NUMERIC(6, 2),
    aum_billion_twd NUMERIC(12, 2),
    expense_ratio_pct NUMERIC(6, 3),
    dividend_frequency VARCHAR(16),
    annual_yield_pct NUMERIC(6, 2),
    return_1m NUMERIC(6, 2),
    return_3m NUMERIC(6, 2),
    return_6m NUMERIC(6, 2),
    return_ytd NUMERIC(6, 2),
    return_1y NUMERIC(6, 2),
    return_3y NUMERIC(6, 2),
    tracking_index TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS etf_constituents (
    etf_symbol VARCHAR(16) NOT NULL REFERENCES etf_profiles(etf_symbol) ON DELETE CASCADE,
    stock_symbol VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64) NOT NULL,
    weight_pct NUMERIC(6, 2) NOT NULL,
    sector VARCHAR(32),
    shares_held_lots BIGINT DEFAULT 0,
    as_of_date DATE NOT NULL DEFAULT CURRENT_DATE,
    PRIMARY KEY (etf_symbol, stock_symbol)
);

CREATE INDEX IF NOT EXISTS idx_etf_constituents_stock ON etf_constituents(stock_symbol, weight_pct DESC);

-- ------------------------------------------------------------------------------
-- 8. User Asset Calculator, Positions, Watchlists & Price/Pattern Alerts
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_portfolios (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cash_twd NUMERIC(18, 2) NOT NULL DEFAULT 1500000.00,
    fee_discount NUMERIC(4, 2) NOT NULL DEFAULT 0.60,
    polling_interval_sec INT NOT NULL DEFAULT 6,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_portfolios(user_id) ON DELETE CASCADE,
    stock_symbol VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64) NOT NULL,
    shares BIGINT NOT NULL CHECK (shares > 0),
    avg_cost_price NUMERIC(14, 4) NOT NULL CHECK (avg_cost_price > 0),
    custom_target_price NUMERIC(14, 4),
    custom_stop_price NUMERIC(14, 4),
    last_recorded_pattern VARCHAR(64),
    notes TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_position UNIQUE (user_id, stock_symbol)
);

CREATE TABLE IF NOT EXISTS user_watchlists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_portfolios(user_id) ON DELETE CASCADE,
    stock_symbol VARCHAR(16) NOT NULL,
    stock_name VARCHAR(64) NOT NULL,
    target_buy_price NUMERIC(14, 4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_watchlist UNIQUE (user_id, stock_symbol)
);

CREATE TABLE IF NOT EXISTS price_pattern_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_portfolios(user_id) ON DELETE CASCADE,
    stock_symbol VARCHAR(16) NOT NULL,
    alert_type VARCHAR(32) NOT NULL,               -- 'TARGET_PRICE_REACHED', 'STOP_LOSS_WARNING', 'KLINE_PATTERN_TRANSITION'
    severity VARCHAR(16) NOT NULL DEFAULT 'MEDIUM',
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    current_price NUMERIC(14, 4) NOT NULL,
    trigger_level NUMERIC(14, 4),
    kline_pattern VARCHAR(64),
    is_read BOOLEAN NOT NULL DEFAULT false,
    triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

