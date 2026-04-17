"""
Pydantic 模型定义

命名规范：
- XxxResponse: API 响应模型
- XxxListResponse: 列表响应（含分页）
- XxxFilter: 查询参数模型
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# === 文章 ===

class ArticleResponse(BaseModel):
    id: int
    source_id: int
    source_name: str        # JOIN sources.name
    url: str
    title: str
    excerpt: Optional[str] = None
    author: Optional[str] = None
    language: str
    country: str
    image_url: Optional[str] = None
    published_at: Optional[datetime] = None  # UTC时间
    published_at_local: Optional[datetime] = None  # 原文当地时间
    published_at_beijing: Optional[datetime] = None  # 北京时间
    crawled_at: datetime
    is_duplicate: bool
    dedup_level: Optional[int] = None
    event_cluster_id: Optional[int] = None
    entities: dict = {}
    categories: list = []

    model_config = {"from_attributes": True}


class ArticleDetailResponse(ArticleResponse):
    content: Optional[str] = None
    content_length: Optional[int] = None
    image_urls: list[str] = []
    external_links: list[str] = []
    title_en: Optional[str] = None
    title_zh: Optional[str] = None
    content_en: Optional[str] = None
    content_zh: Optional[str] = None
    duplicate_of: Optional[int] = None


class ArticleListResponse(BaseModel):
    items: list[ArticleResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


# === 信息源 ===

class SourceResponse(BaseModel):
    id: int
    url: str
    name: str
    domain: str
    country: str
    language: str
    region: Optional[str] = None
    tier: int
    rendering: str
    has_rss: bool
    priority: str
    status: str
    crawl_interval_minutes: int
    last_crawl_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    avg_articles_per_crawl: float
    avg_articles_per_day: float
    discovery_rate: float
    crawl_count: int  # 累计抓取次数
    articles_last_24h: int = 0  # 过去24小时抓取的文章数
    consecutive_errors: int
    error_count: int
    last_error: Optional[str] = None
    last_error_type: Optional[str] = None
    days_without_new: int

    model_config = {"from_attributes": True}


class SourceListResponse(BaseModel):
    items: list[SourceResponse]
    total: int


# === 统计 ===

class StatsResponse(BaseModel):
    total_sources: int
    active_sources: int
    degraded_sources: int
    paused_sources: int
    total_articles: int
    articles_today: int
    duplicates_today: int
    unique_today: int
    languages: list[dict]    # [{language: "en", count: 500}, ...]
    countries: list[dict]    # [{country: "US", count: 300}, ...]


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str            # "connected" | "error"
    sources_active: int
    last_crawl_at: Optional[datetime] = None