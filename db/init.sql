-- ============================================
-- GlobalAutoNews 数据库初始化
-- ============================================

-- 启用扩展
-- CREATE EXTENSION IF NOT EXISTS vector;  -- 注释掉，本地环境可能没有安装 pgvector
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================
-- 1. 信息源表 (sources)
-- ============================================
CREATE TABLE sources (
    id SERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    domain TEXT NOT NULL,
    country VARCHAR(5) NOT NULL,
    language VARCHAR(10) NOT NULL,
    region VARCHAR(50),

    -- 抓取配置
    tier INTEGER DEFAULT 1 CHECK (tier IN (1, 2, 3)),
    rendering VARCHAR(10) DEFAULT 'static' CHECK (rendering IN ('static', 'dynamic')),
    rss_url TEXT,
    has_rss BOOLEAN DEFAULT FALSE,
    adapter_config JSONB,

    -- 调度参数
    priority VARCHAR(10) DEFAULT 'medium' CHECK (priority IN ('high', 'medium', 'low')),
    crawl_interval_minutes INTEGER DEFAULT 240,
    next_crawl_at TIMESTAMPTZ,
    last_crawl_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,

    -- 学习到的模式
    avg_articles_per_crawl FLOAT DEFAULT 0,
    avg_articles_per_day FLOAT DEFAULT 0,
    publish_hours JSONB,
    publish_weekdays JSONB,
    discovery_rate FLOAT DEFAULT 0,

    -- 状态与健康管理
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'degraded', 'paused', 'archived', 'pending')),
    consecutive_errors INTEGER DEFAULT 0,
    last_error TEXT,
    last_error_type VARCHAR(20) CHECK (last_error_type IN ('http_error', 'extract_empty', 'timeout', 'unknown', NULL)),
    error_count INTEGER DEFAULT 0,
    days_without_new INTEGER DEFAULT 0,
    degraded_at TIMESTAMPTZ,
    paused_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sources_next_crawl ON sources(next_crawl_at) WHERE status IN ('active', 'degraded');
CREATE INDEX idx_sources_country ON sources(country);
CREATE INDEX idx_sources_language ON sources(language);
CREATE INDEX idx_sources_status ON sources(status);
CREATE INDEX idx_sources_domain ON sources(domain);

-- ============================================
-- 2. 文章表 (articles)
-- ============================================
CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,

    -- 标识与去重
    url TEXT UNIQUE NOT NULL,
    url_hash VARCHAR(64) NOT NULL,
    title TEXT NOT NULL,
    title_simhash BIGINT,

    -- 内容
    content TEXT,
    content_length INTEGER,
    excerpt TEXT,
    author TEXT,
    image_url TEXT,
    image_urls JSONB DEFAULT '[]',

    -- 分类与标注
    language VARCHAR(10) NOT NULL,
    country VARCHAR(5) NOT NULL,
    entities JSONB DEFAULT '{}',
    categories JSONB DEFAULT '[]',

    -- 跨语种聚合
    event_cluster_id INTEGER,
    embedding BYTEA,  -- 改为 BYTEA 类型，兼容无 pgvector 环境

    -- 翻译（按需填充）
    title_en TEXT,
    title_zh TEXT,
    content_en TEXT,
    content_zh TEXT,

    -- 去重结果
    is_duplicate BOOLEAN DEFAULT FALSE,
    duplicate_of INTEGER,
    dedup_level INTEGER CHECK (dedup_level IN (1, 2, 3, 4, NULL)),

    -- 时间
    published_at TIMESTAMPTZ,
    crawled_at TIMESTAMPTZ DEFAULT NOW(),

    -- 元数据
    external_links JSONB DEFAULT '[]',
    raw_html_path TEXT,
    metadata JSONB DEFAULT '{}',

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_articles_url_hash ON articles(url_hash);
CREATE INDEX idx_articles_title_simhash ON articles(title_simhash);
CREATE INDEX idx_articles_source ON articles(source_id);
CREATE INDEX idx_articles_published ON articles(published_at DESC);
CREATE INDEX idx_articles_language ON articles(language);
CREATE INDEX idx_articles_country ON articles(country);
CREATE INDEX idx_articles_cluster ON articles(event_cluster_id);
CREATE INDEX idx_articles_not_dup ON articles(published_at DESC) WHERE is_duplicate = FALSE;
CREATE INDEX idx_articles_crawled ON articles(crawled_at DESC);

-- 全文搜索索引（英文+通用）
CREATE INDEX idx_articles_title_trgm ON articles USING gin(title gin_trgm_ops);

-- ============================================
-- 3. 事件簇表 (event_clusters)
-- ============================================
CREATE TABLE event_clusters (
    id SERIAL PRIMARY KEY,
    representative_id INTEGER REFERENCES articles(id) ON DELETE SET NULL,

    title_en TEXT,
    title_zh TEXT,
    summary_en TEXT,
    summary_zh TEXT,

    article_count INTEGER DEFAULT 1,
    language_count INTEGER DEFAULT 1,
    country_count INTEGER DEFAULT 1,
    languages JSONB DEFAULT '[]',
    countries JSONB DEFAULT '[]',

    key_entities JSONB DEFAULT '{}',
    importance_score FLOAT DEFAULT 0,

    first_seen_at TIMESTAMPTZ,
    last_updated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_updated ON event_clusters(last_updated_at DESC);
CREATE INDEX idx_events_importance ON event_clusters(importance_score DESC);

-- 添加外键（articles → event_clusters 需要 event_clusters 表先存在）
ALTER TABLE articles ADD CONSTRAINT fk_articles_cluster
    FOREIGN KEY (event_cluster_id) REFERENCES event_clusters(id) ON DELETE SET NULL;

-- ============================================
-- 4. 候选新源表 (source_candidates)
-- ============================================
CREATE TABLE source_candidates (
    id SERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    domain TEXT NOT NULL,

    mention_count INTEGER DEFAULT 1,
    discovered_from JSONB DEFAULT '[]',
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),

    auto_analysis JSONB,
    is_automotive BOOLEAN,
    estimated_language VARCHAR(10),
    estimated_country VARCHAR(5),
    estimated_update_freq TEXT,
    content_uniqueness_score FLOAT,

    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'auto_added')),
    reviewed_at TIMESTAMPTZ,
    reviewer_notes TEXT,
    approved_source_id INTEGER REFERENCES sources(id),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_candidates_status ON source_candidates(status);
CREATE INDEX idx_candidates_mentions ON source_candidates(mention_count DESC);
CREATE INDEX idx_candidates_domain ON source_candidates(domain);

-- ============================================
-- 5. 抓取日志表 (crawl_logs)
-- ============================================
CREATE TABLE crawl_logs (
    id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,

    status VARCHAR(20) NOT NULL CHECK (status IN ('success', 'error', 'timeout', 'skipped')),
    tier_used INTEGER,
    articles_found INTEGER DEFAULT 0,
    articles_new INTEGER DEFAULT 0,
    articles_duplicate INTEGER DEFAULT 0,

    response_time_ms INTEGER,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_crawl_logs_source ON crawl_logs(source_id, created_at DESC);
CREATE INDEX idx_crawl_logs_created ON crawl_logs(created_at DESC);

-- ============================================
-- 辅助函数
-- ============================================

-- 自动更新 updated_at 触发器
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_sources_updated_at
    BEFORE UPDATE ON sources
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- 清理旧日志（保留30天）
CREATE OR REPLACE FUNCTION cleanup_old_crawl_logs()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM crawl_logs WHERE created_at < NOW() - INTERVAL '30 days';
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;