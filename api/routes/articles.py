"""
文章 API

端点：
    GET /api/articles           — 文章列表（支持筛选和分页）
    GET /api/articles/{id}      — 文章详情

筛选参数（Query Parameters）：
    language: str = None        — 按语种筛选 (如 "en", "ja")
    country: str = None         — 按国家筛选 (如 "US", "JP")
    source_id: int = None       — 按信息源筛选
    is_duplicate: bool = None   — 是否显示重复文章（默认 False，即只显示非重复）
    search: str = None          — 标题模糊搜索（使用 pg_trgm）
    date_from: date = None      — 起始日期
    date_to: date = None        — 结束日期
    page: int = 1               — 页码
    page_size: int = 20         — 每页条数（最大 100）
    sort_by: str = "crawled_at" — 排序字段 (crawled_at | published_at)
"""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Article, Source
from api.database import get_db
from api.models.schemas import (
    ArticleResponse, ArticleDetailResponse, ArticleListResponse
)
from api.config import PAGE_SIZE, MAX_PAGE_SIZE
from api.services.translate import get_translation_service

router = APIRouter()


class TranslateRequest(BaseModel):
    target_language: str  # "zh", "en", etc.


class TranslateResponse(BaseModel):
    success: bool
    title_translated: Optional[str]
    content_translated: Optional[str]
    source_language: str
    target_language: str
    engine: str


@router.get("/articles", response_model=ArticleListResponse)
async def get_articles(
    language: Optional[str] = Query(None, description="按语种筛选 (如 'en', 'ja')"),
    country: Optional[str] = Query(None, description="按国家筛选 (如 'US', 'JP')"),
    source_id: Optional[int] = Query(None, description="按信息源筛选"),
    is_duplicate: Optional[bool] = Query(False, description="是否显示重复文章"),
    search: Optional[str] = Query(None, description="标题模糊搜索"),
    date_from: Optional[date] = Query(None, description="起始日期"),
    date_to: Optional[date] = Query(None, description="结束日期"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
    sort_by: str = Query("crawled_at", description="排序字段 (crawled_at | published_at)"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取文章列表，支持筛选和分页
    """
    # 构建查询
    query = select(Article, Source.name.label("source_name")).join(
        Source, Article.source_id == Source.id
    )
    
    # 应用筛选条件
    conditions = []
    
    if language:
        conditions.append(Article.language == language)
    
    if country:
        conditions.append(Article.country == country)
    
    if source_id:
        conditions.append(Article.source_id == source_id)
    
    if is_duplicate is not None:
        conditions.append(Article.is_duplicate == is_duplicate)
    
    if search:
        # 使用 pg_trgm 进行模糊搜索
        conditions.append(Article.title.ilike(f"%{search}%"))
    
    if date_from:
        conditions.append(Article.published_at >= datetime.combine(date_from, datetime.min.time()))
    
    if date_to:
        conditions.append(Article.published_at <= datetime.combine(date_to, datetime.max.time()))
    
    if conditions:
        query = query.where(and_(*conditions))
    
    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # 排序
    if sort_by == "published_at":
        order_by = Article.published_at.desc()
    else:
        order_by = Article.crawled_at.desc()
    
    query = query.order_by(order_by)
    
    # 分页
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    # 执行查询
    result = await db.execute(query)
    rows = result.all()
    
    # 构建响应
    items = []
    for article, source_name in rows:
        item = ArticleResponse(
            id=article.id,
            source_id=article.source_id,
            source_name=source_name,
            url=article.url,
            title=article.title,
            excerpt=article.excerpt,
            author=article.author,
            language=article.language,
            country=article.country,
            image_url=article.image_url,
            published_at=article.published_at,
            crawled_at=article.crawled_at,
            is_duplicate=article.is_duplicate,
            dedup_level=article.dedup_level,
            event_cluster_id=article.event_cluster_id,
            entities=article.entities or {},
            categories=article.categories or [],
        )
        items.append(item)
    
    return ArticleListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + page_size) < total,
    )


@router.get("/articles/{article_id}", response_model=ArticleDetailResponse)
async def get_article(
    article_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    获取文章详情
    """
    # 查询文章
    query = select(Article, Source.name.label("source_name")).join(
        Source, Article.source_id == Source.id
    ).where(Article.id == article_id)
    
    result = await db.execute(query)
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=404, detail="Article not found")
    
    article, source_name = row
    
    return ArticleDetailResponse(
        id=article.id,
        source_id=article.source_id,
        source_name=source_name,
        url=article.url,
        title=article.title,
        excerpt=article.excerpt,
        author=article.author,
        language=article.language,
        country=article.country,
        image_url=article.image_url,
        published_at=article.published_at,
        crawled_at=article.crawled_at,
        is_duplicate=article.is_duplicate,
        dedup_level=article.dedup_level,
        event_cluster_id=article.event_cluster_id,
        entities=article.entities or {},
        categories=article.categories or [],
        content=article.content,
        content_length=article.content_length,
        image_urls=article.image_urls or [],
        external_links=article.external_links or [],
        title_en=article.title_en,
        title_zh=article.title_zh,
        content_en=article.content_en,
        content_zh=article.content_zh,
        duplicate_of=article.duplicate_of,
    )


@router.post("/articles/{article_id}/translate", response_model=TranslateResponse)
async def translate_article(
    article_id: int,
    request: TranslateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    按需翻译文章标题和内容
    """
    # 获取文章
    result = await db.execute(select(Article).where(Article.id == article_id))
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    # 确定目标字段
    target_language = request.target_language
    if target_language not in ["zh", "en"]:
        raise HTTPException(status_code=400, detail="target_language must be 'zh' or 'en'")

    title_field = f"title_{target_language}"
    content_field = f"content_{target_language}"

    # 检查是否已翻译
    if getattr(article, title_field):
        return TranslateResponse(
            success=True,
            title_translated=getattr(article, title_field),
            content_translated=getattr(article, content_field),
            source_language=article.language or "unknown",
            target_language=target_language,
            engine="cached",
        )

    # 获取翻译服务
    translator = get_translation_service()

    # 翻译标题
    title_translated = ""
    if article.title:
        title_translated, detected_lang = await translator.translate(
            article.title,
            target_language=target_language,
            source_language=article.language
        )
        setattr(article, title_field, title_translated)

    # 翻译内容（前 2000 字符）
    content_translated = ""
    if article.content:
        content_to_translate = article.content[:2000]
        content_translated, _ = await translator.translate(
            content_to_translate,
            target_language=target_language,
            source_language=article.language
        )
        setattr(article, content_field, content_translated)

    await db.commit()

    return TranslateResponse(
        success=True,
        title_translated=title_translated,
        content_translated=content_translated,
        source_language=article.language or "unknown",
        target_language=target_language,
        engine=translator.get_engine(),
    )