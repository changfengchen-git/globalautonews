"""
信息源 API

端点：
    GET  /api/sources            — 信息源列表（支持按 country, language, status 筛选）
    GET  /api/sources/{id}       — 信息源详情
    GET  /api/sources/{id}/health — 单个信息源的健康状态和最近抓取日志
    PATCH /api/sources/{id}      — 更新信息源（可更新 status, priority, tier, crawl_interval_minutes）
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Source, CrawlLog, Article
from api.database import get_db
from api.models.schemas import SourceResponse, SourceListResponse

router = APIRouter()


class SourceUpdate(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    tier: Optional[int] = None
    crawl_interval_minutes: Optional[int] = None


@router.get("/sources", response_model=SourceListResponse)
async def get_sources(
    country: Optional[str] = Query(None, description="按国家筛选"),
    language: Optional[str] = Query(None, description="按语种筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取信息源列表
    """
    # 构建查询
    query = select(Source)
    
    # 应用筛选条件
    conditions = []
    
    if country:
        conditions.append(Source.country == country)
    
    if language:
        conditions.append(Source.language == language)
    
    if status:
        conditions.append(Source.status == status)
    
    if conditions:
        query = query.where(*conditions)
    
    # 计算总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # 排序和分页
    query = query.order_by(Source.id)
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    # 执行查询
    result = await db.execute(query)
    sources = result.scalars().all()
    
    # 计算过去24小时的文章数量
    twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    
    # 构建响应
    items = []
    for source in sources:
        # 查询该信息源过去24小时的文章数量
        articles_24h_query = select(func.count()).where(
            Article.source_id == source.id,
            Article.crawled_at >= twenty_four_hours_ago
        )
        articles_24h_result = await db.execute(articles_24h_query)
        articles_last_24h = articles_24h_result.scalar() or 0
        
        item = SourceResponse(
            id=source.id,
            url=source.url,
            name=source.name,
            domain=source.domain,
            country=source.country,
            language=source.language,
            region=source.region,
            tier=source.tier,
            rendering=source.rendering,
            has_rss=source.has_rss,
            priority=source.priority,
            status=source.status,
            crawl_interval_minutes=source.crawl_interval_minutes,
            last_crawl_at=source.last_crawl_at,
            last_success_at=source.last_success_at,
            avg_articles_per_crawl=source.avg_articles_per_crawl,
            avg_articles_per_day=source.avg_articles_per_day,
            discovery_rate=source.discovery_rate,
            crawl_count=source.crawl_count,
            articles_last_24h=articles_last_24h,
            consecutive_errors=source.consecutive_errors,
            error_count=source.error_count,
            last_error=source.last_error,
            last_error_type=source.last_error_type,
            days_without_new=source.days_without_new,
        )
        items.append(item)
    
    return SourceListResponse(
        items=items,
        total=total,
    )


@router.get("/sources/needs-repair")
async def get_sources_needs_repair(
    db: AsyncSession = Depends(get_db),
):
    """
    获取需要修复的站点列表（last_error_type='extract_empty'）
    """
    result = await db.execute(
        select(Source)
        .where(Source.last_error_type == 'extract_empty')
        .where(Source.status.in_(["active", "degraded"]))
        .order_by(Source.consecutive_errors.desc())
    )
    sources = result.scalars().all()

    return {
        "items": [
            {
                "id": s.id,
                "name": s.name,
                "domain": s.domain,
                "consecutive_errors": s.consecutive_errors,
                "last_success_at": s.last_success_at,
                "last_error": s.last_error,
            }
            for s in sources
        ],
        "total": len(sources),
    }


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    获取信息源详情
    """
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    return SourceResponse(
        id=source.id,
        url=source.url,
        name=source.name,
        domain=source.domain,
        country=source.country,
        language=source.language,
        region=source.region,
        tier=source.tier,
        rendering=source.rendering,
        has_rss=source.has_rss,
        priority=source.priority,
        status=source.status,
        crawl_interval_minutes=source.crawl_interval_minutes,
        last_crawl_at=source.last_crawl_at,
        last_success_at=source.last_success_at,
        avg_articles_per_crawl=source.avg_articles_per_crawl,
        avg_articles_per_day=source.avg_articles_per_day,
        discovery_rate=source.discovery_rate,
        consecutive_errors=source.consecutive_errors,
        error_count=source.error_count,
        last_error=source.last_error,
        last_error_type=source.last_error_type,
        days_without_new=source.days_without_new,
    )


@router.get("/sources/{source_id}/health")
async def get_source_health(
    source_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    获取单个信息源的健康状态和最近抓取日志
    """
    # 获取 source
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    # 获取最近 10 次抓取日志
    logs_query = (
        select(CrawlLog)
        .where(CrawlLog.source_id == source_id)
        .order_by(desc(CrawlLog.created_at))
        .limit(10)
    )
    logs_result = await db.execute(logs_query)
    logs = logs_result.scalars().all()
    
    # 计算成功率
    total_logs = len(logs)
    success_logs = sum(1 for log in logs if log.status == "success")
    success_rate = (success_logs / total_logs * 100) if total_logs > 0 else 0
    
    return {
        "source": SourceResponse(
            id=source.id,
            url=source.url,
            name=source.name,
            domain=source.domain,
            country=source.country,
            language=source.language,
            region=source.region,
            tier=source.tier,
            rendering=source.rendering,
            has_rss=source.has_rss,
            priority=source.priority,
            status=source.status,
            crawl_interval_minutes=source.crawl_interval_minutes,
            last_crawl_at=source.last_crawl_at,
            last_success_at=source.last_success_at,
            avg_articles_per_crawl=source.avg_articles_per_crawl,
            avg_articles_per_day=source.avg_articles_per_day,
            discovery_rate=source.discovery_rate,
            consecutive_errors=source.consecutive_errors,
            error_count=source.error_count,
            last_error=source.last_error,
            last_error_type=source.last_error_type,
            days_without_new=source.days_without_new,
        ),
        "health": {
            "status": source.status,
            "consecutive_errors": source.consecutive_errors,
            "last_error": source.last_error,
            "last_error_type": source.last_error_type,
            "success_rate": round(success_rate, 2),
            "recent_logs": [
                {
                    "id": log.id,
                    "status": log.status,
                    "started_at": log.started_at,
                    "completed_at": log.completed_at,
                    "articles_found": log.articles_found,
                    "articles_new": log.articles_new,
                    "error_message": log.error_message,
                }
                for log in logs
            ],
        },
    }


@router.patch("/sources/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: int,
    update: SourceUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    更新信息源
    """
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    # 更新字段
    if update.status is not None:
        if update.status not in ["active", "degraded", "paused", "archived", "pending"]:
            raise HTTPException(status_code=400, detail="Invalid status")
        source.status = update.status
    
    if update.priority is not None:
        if update.priority not in ["high", "medium", "low"]:
            raise HTTPException(status_code=400, detail="Invalid priority")
        source.priority = update.priority
    
    if update.tier is not None:
        if update.tier not in [1, 2, 3]:
            raise HTTPException(status_code=400, detail="Invalid tier")
        source.tier = update.tier
    
    if update.crawl_interval_minutes is not None:
        if update.crawl_interval_minutes < 1:
            raise HTTPException(status_code=400, detail="crawl_interval_minutes must be >= 1")
        source.crawl_interval_minutes = update.crawl_interval_minutes
    
    source.updated_at = datetime.now()
    
    await db.commit()
    await db.refresh(source)
    
    return SourceResponse(
        id=source.id,
        url=source.url,
        name=source.name,
        domain=source.domain,
        country=source.country,
        language=source.language,
        region=source.region,
        tier=source.tier,
        rendering=source.rendering,
        has_rss=source.has_rss,
        priority=source.priority,
        status=source.status,
        crawl_interval_minutes=source.crawl_interval_minutes,
        last_crawl_at=source.last_crawl_at,
        last_success_at=source.last_success_at,
        avg_articles_per_crawl=source.avg_articles_per_crawl,
        avg_articles_per_day=source.avg_articles_per_day,
        discovery_rate=source.discovery_rate,
        consecutive_errors=source.consecutive_errors,
        error_count=source.error_count,
        last_error=source.last_error,
        last_error_type=source.last_error_type,
        days_without_new=source.days_without_new,
    )


@router.post("/sources/{source_id}/retry")
async def retry_source(
    source_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    手动触发一次抓取
    """
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # 重置下次抓取时间为现在
    source.next_crawl_at = datetime.now()

    await db.commit()

    return {"success": True, "message": f"Source #{source_id} scheduled for crawl"}


@router.post("/sources/{source_id}/upgrade-tier")
async def upgrade_source_tier(
    source_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    升级站点到 Tier 2
    """
    result = await db.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()

    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if source.tier >= 2:
        raise HTTPException(status_code=400, detail="Source already tier 2 or higher")

    source.tier = 2
    source.rendering = "dynamic"  # Tier 2 使用动态渲染
    source.consecutive_errors = 0  # 重置错误计数

    await db.commit()

    return {"success": True, "message": f"Source #{source_id} upgraded to tier 2"}