"""
SQLAlchemy ORM 模型定义

所有模型与 db/init.sql 中的表结构完全对应。
使用 SQLAlchemy 2.0 Mapped 声明式风格。
"""
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str] = mapped_column(String(5), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String(50))

    # 抓取配置
    tier: Mapped[int] = mapped_column(Integer, default=1)
    rendering: Mapped[str] = mapped_column(String(10), default="static")
    rss_url: Mapped[Optional[str]] = mapped_column(Text)
    has_rss: Mapped[bool] = mapped_column(Boolean, default=False)
    adapter_config: Mapped[Optional[dict]] = mapped_column(JSONB)

    # 调度参数
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    crawl_interval_minutes: Mapped[int] = mapped_column(Integer, default=240)
    next_crawl_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_crawl_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # 学习到的模式
    avg_articles_per_crawl: Mapped[float] = mapped_column(Float, default=0)
    avg_articles_per_day: Mapped[float] = mapped_column(Float, default=0)
    publish_hours: Mapped[Optional[dict]] = mapped_column(JSONB)
    publish_weekdays: Mapped[Optional[dict]] = mapped_column(JSONB)
    discovery_rate: Mapped[float] = mapped_column(Float, default=0)

    # 状态与健康
    status: Mapped[str] = mapped_column(String(20), default="active")
    crawl_count: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_errors: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    last_error_type: Mapped[Optional[str]] = mapped_column(String(20))
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    days_without_new: Mapped[int] = mapped_column(Integer, default=0)
    degraded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    paused_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    articles: Mapped[list["Article"]] = relationship(back_populates="source")
    crawl_logs: Mapped[list["CrawlLog"]] = relationship(back_populates="source")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))

    # 标识与去重
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_simhash: Mapped[Optional[int]] = mapped_column(BigInteger)  # BigInteger 对应 BIGINT

    # 内容
    content: Mapped[Optional[str]] = mapped_column(Text)
    content_length: Mapped[Optional[int]] = mapped_column(Integer)
    excerpt: Mapped[Optional[str]] = mapped_column(Text)
    author: Mapped[Optional[str]] = mapped_column(Text)
    image_url: Mapped[Optional[str]] = mapped_column(Text)
    image_urls: Mapped[Optional[list]] = mapped_column(JSONB, default=list)

    # 分类与标注
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    country: Mapped[str] = mapped_column(String(5), nullable=False)
    entities: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    categories: Mapped[Optional[list]] = mapped_column(JSONB, default=list)

    # 跨语种聚合
    event_cluster_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("event_clusters.id", ondelete="SET NULL")
    )
    embedding = mapped_column(Vector(256), nullable=True)

    # 翻译
    title_en: Mapped[Optional[str]] = mapped_column(Text)
    title_zh: Mapped[Optional[str]] = mapped_column(Text)
    content_en: Mapped[Optional[str]] = mapped_column(Text)
    content_zh: Mapped[Optional[str]] = mapped_column(Text)

    # 去重结果
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_of: Mapped[Optional[int]] = mapped_column(Integer)
    dedup_level: Mapped[Optional[int]] = mapped_column(Integer)

    # 时间
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 元数据
    external_links: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    raw_html_path: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 关系
    source: Mapped["Source"] = relationship(back_populates="articles")
    event_cluster: Mapped[Optional["EventCluster"]] = relationship(
        back_populates="articles",
        foreign_keys=[event_cluster_id]
    )


class EventCluster(Base):
    __tablename__ = "event_clusters"

    id: Mapped[int] = mapped_column(primary_key=True)
    representative_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("articles.id", ondelete="SET NULL")
    )

    title_en: Mapped[Optional[str]] = mapped_column(Text)
    title_zh: Mapped[Optional[str]] = mapped_column(Text)
    summary_en: Mapped[Optional[str]] = mapped_column(Text)
    summary_zh: Mapped[Optional[str]] = mapped_column(Text)

    article_count: Mapped[int] = mapped_column(Integer, default=1)
    language_count: Mapped[int] = mapped_column(Integer, default=1)
    country_count: Mapped[int] = mapped_column(Integer, default=1)
    languages: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    countries: Mapped[Optional[list]] = mapped_column(JSONB, default=list)

    key_entities: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)
    importance_score: Mapped[float] = mapped_column(Float, default=0)

    first_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 关系
    articles: Mapped[list["Article"]] = relationship(
        back_populates="event_cluster",
        foreign_keys="Article.event_cluster_id"
    )


class SourceCandidate(Base):
    __tablename__ = "source_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)

    mention_count: Mapped[int] = mapped_column(Integer, default=1)
    discovered_from: Mapped[Optional[list]] = mapped_column(JSONB, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    auto_analysis: Mapped[Optional[dict]] = mapped_column(JSONB)
    is_automotive: Mapped[Optional[bool]] = mapped_column(Boolean)
    estimated_language: Mapped[Optional[str]] = mapped_column(String(10))
    estimated_country: Mapped[Optional[str]] = mapped_column(String(5))
    estimated_update_freq: Mapped[Optional[str]] = mapped_column(Text)
    content_uniqueness_score: Mapped[Optional[float]] = mapped_column(Float)

    status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reviewer_notes: Mapped[Optional[str]] = mapped_column(Text)
    approved_source_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("sources.id")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    tier_used: Mapped[Optional[int]] = mapped_column(Integer)
    articles_found: Mapped[int] = mapped_column(Integer, default=0)
    articles_new: Mapped[int] = mapped_column(Integer, default=0)
    articles_duplicate: Mapped[int] = mapped_column(Integer, default=0)

    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # 关系
    source: Mapped["Source"] = relationship(back_populates="crawl_logs")