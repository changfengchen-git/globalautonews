"""
事件 API

端点：
    GET /api/events              — 事件列表（按 importance_score 排序）
    GET /api/events/{id}         — 事件详情（含所有关联文章）
"""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Article, EventCluster, Source
from api.database import get_db

router = APIRouter()


class ArticleSummary(BaseModel):
    id: int
    source_id: int
    source_name: str
    source_country: Optional[str]
    url: str
    title: str
    title_en: Optional[str]
    title_zh: Optional[str]
    excerpt: Optional[str]
    language: str
    country: Optional[str]
    image_url: Optional[str]
    published_at: Optional[str]
    crawled_at: str
    is_duplicate: bool

    class Config:
        from_attributes = True


class EventResponse(BaseModel):
    id: int
    article_count: int
    language_count: int
    country_count: int
    languages: List[str]
    countries: List[str]
    importance_score: float
    representative_title: str
    representative_url: Optional[str]
    created_at: str
    updated_at: str


class EventDetailResponse(BaseModel):
    id: int
    article_count: int
    language_count: int
    country_count: int
    languages: List[str]
    countries: List[str]
    importance_score: float
    articles: List[ArticleSummary]
    created_at: str
    updated_at: str


class EventListResponse(BaseModel):
    items: List[EventResponse]
    total: int
    page: int
    page_size: int


@router.get("/events", response_model=EventListResponse)
async def get_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    获取事件列表（按 importance_score 排序）
    """
    # 计算总数
    count_result = await db.execute(select(func.count()).select_from(EventCluster))
    total = count_result.scalar() or 0

    # 查询事件
    query = (
        select(EventCluster, Article.title.label("rep_title"), Article.url.label("rep_url"))
        .outerjoin(Article, EventCluster.representative_id == Article.id)
        .order_by(desc(EventCluster.importance_score))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(query)
    rows = result.all()

    items = []
    for cluster, rep_title, rep_url in rows:
        items.append(EventResponse(
            id=cluster.id,
            article_count=cluster.article_count or 0,
            language_count=cluster.language_count or 0,
            country_count=cluster.country_count or 0,
            languages=cluster.languages or [],
            countries=cluster.countries or [],
            importance_score=cluster.importance_score or 0,
            representative_title=rep_title or "",
            representative_url=rep_url,
            created_at=cluster.created_at.isoformat() if cluster.created_at else "",
            updated_at=cluster.updated_at.isoformat() if cluster.updated_at else "",
        ))

    return EventListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/events/{event_id}", response_model=EventDetailResponse)
async def get_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    获取事件详情（含所有关联文章）
    """
    # 查询事件
    result = await db.execute(
        select(EventCluster).where(EventCluster.id == event_id)
    )
    cluster = result.scalar_one_or_none()

    if not cluster:
        raise HTTPException(status_code=404, detail="Event not found")

    # 查询关联文章
    articles_query = (
        select(Article, Source.name.label("source_name"))
        .join(Source, Article.source_id == Source.id)
        .where(Article.event_cluster_id == event_id)
        .order_by(desc(Article.published_at))
    )

    result = await db.execute(articles_query)
    rows = result.all()

    articles = []
    for article, source_name in rows:
        articles.append(ArticleSummary(
            id=article.id,
            source_id=article.source_id,
            source_name=source_name,
            source_country=article.country,
            url=article.url,
            title=article.title,
            title_en=article.title_en,
            title_zh=article.title_zh,
            excerpt=article.excerpt,
            language=article.language or "unknown",
            country=article.country,
            image_url=article.image_url,
            published_at=article.published_at.isoformat() if article.published_at else None,
            crawled_at=article.crawled_at.isoformat() if article.crawled_at else "",
            is_duplicate=article.is_duplicate or False,
        ))

    return EventDetailResponse(
        id=cluster.id,
        article_count=cluster.article_count or 0,
        language_count=cluster.language_count or 0,
        country_count=cluster.country_count or 0,
        languages=cluster.languages or [],
        countries=cluster.countries or [],
        importance_score=cluster.importance_score or 0,
        articles=articles,
        created_at=cluster.created_at.isoformat() if cluster.created_at else "",
        updated_at=cluster.updated_at.isoformat() if cluster.updated_at else "",
    )
