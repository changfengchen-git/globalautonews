"""
系统健康 API

端点：
    GET /api/health    — 系统健康检查（检查数据库连接）
    GET /api/stats     — 系统统计数据
"""
from datetime import datetime, date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Source, Article
from api.database import get_db
from api.models.schemas import HealthResponse, StatsResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check(
    db: AsyncSession = Depends(get_db),
):
    """
    系统健康检查
    """
    try:
        # 检查数据库连接
        await db.execute(select(func.count()).select_from(Source))
        database_status = "connected"
        
        # 获取活跃信息源数量
        result = await db.execute(
            select(func.count()).select_from(Source).where(Source.status == "active")
        )
        sources_active = result.scalar()
        
        # 获取最近抓取时间
        result = await db.execute(
            select(func.max(Source.last_crawl_at))
        )
        last_crawl_at = result.scalar()
        
    except Exception as e:
        database_status = f"error: {str(e)}"
        sources_active = 0
        last_crawl_at = None
    
    return HealthResponse(
        status="ok",
        version="0.1.0",
        database=database_status,
        sources_active=sources_active,
        last_crawl_at=last_crawl_at,
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
):
    """
    获取系统统计数据
    """
    # 信息源统计
    sources_result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Source.status == "active").label("active"),
            func.count().filter(Source.status == "degraded").label("degraded"),
            func.count().filter(Source.status == "paused").label("paused"),
        ).select_from(Source)
    )
    sources_stats = sources_result.first()
    
    # 文章统计
    articles_result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Article.crawled_at >= datetime.now() - timedelta(days=1)).label("today"),
            func.count().filter(
                and_(
                    Article.is_duplicate == True,
                    Article.crawled_at >= datetime.now() - timedelta(days=1)
                )
            ).label("duplicates_today"),
            func.count().filter(
                and_(
                    Article.is_duplicate == False,
                    Article.crawled_at >= datetime.now() - timedelta(days=1)
                )
            ).label("unique_today"),
        ).select_from(Article)
    )
    articles_stats = articles_result.first()
    
    # 语言分布
    languages_result = await db.execute(
        select(
            Article.language,
            func.count().label("count")
        )
        .group_by(Article.language)
        .order_by(func.count().desc())
        .limit(10)
    )
    languages = [{"language": row[0], "count": row[1]} for row in languages_result]
    
    # 国家分布
    countries_result = await db.execute(
        select(
            Article.country,
            func.count().label("count")
        )
        .group_by(Article.country)
        .order_by(func.count().desc())
        .limit(10)
    )
    countries = [{"country": row[0], "count": row[1]} for row in countries_result]
    
    return StatsResponse(
        total_sources=sources_stats.total,
        active_sources=sources_stats.active,
        degraded_sources=sources_stats.degraded,
        paused_sources=sources_stats.paused,
        total_articles=articles_stats.total,
        articles_today=articles_stats.today,
        duplicates_today=articles_stats.duplicates_today,
        unique_today=articles_stats.unique_today,
        languages=languages,
        countries=countries,
    )