"""
站点健康生命周期管理

实现 active → degraded → paused → archived 的完整生命周期管理。

功能：
1. 每次抓取后的状态转换
2. 每日任务：检查长期无新文章的站点
3. 周检探活：对 paused 站点进行 HTTP 探测
4. 爬虫失效检测
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from shared.models import Source, CrawlLog

logger = logging.getLogger("crawler.engine.health")


class HealthManager:
    """站点健康生命周期管理器"""

    def __init__(self, engine):
        """
        初始化健康管理器。

        参数:
            engine: SQLAlchemy async engine
        """
        self.engine = engine

    def update_health_after_crawl(
        self,
        source: Source,
        success: bool,
        articles_new: int = 0,
        error_type: Optional[str] = None
    ) -> None:
        """
        每次抓取后更新站点健康状态。

        参数:
            source: Source 对象
            success: 是否成功
            articles_new: 新文章数量
            error_type: 错误类型
        """
        now = datetime.now(timezone.utc)

        if success:
            # 成功：恢复状态
            source.status = 'active'
            source.consecutive_errors = 0
            source.last_success_at = now

            # 更新无新文章天数
            if articles_new > 0:
                source.days_without_new = 0
            else:
                source.days_without_new = (source.days_without_new or 0) + 1

            # 清除错误信息
            source.last_error = None
            source.last_error_type = None

        else:
            # 失败：增加错误计数
            source.consecutive_errors = (source.consecutive_errors or 0) + 1
            source.last_error_type = error_type

            # 状态转换
            if source.consecutive_errors >= 15 and source.status == 'degraded':
                source.status = 'paused'
                source.paused_at = now
                logger.info(
                    f"Source #{source.id} ({source.name}) paused "
                    f"after {source.consecutive_errors} consecutive errors"
                )

            elif source.consecutive_errors >= 5 and source.status == 'active':
                source.status = 'degraded'
                source.degraded_at = now
                logger.info(
                    f"Source #{source.id} ({source.name}) degraded "
                    f"after {source.consecutive_errors} consecutive errors"
                )

            # 更新无新文章天数
            source.days_without_new = (source.days_without_new or 0) + 1

    async def run_daily_check(self) -> Dict[str, int]:
        """
        每日任务：检查长期无新文章的站点。

        返回:
            统计信息字典
        """
        stats = {
            "priority_low": 0,
            "archived": 0,
        }

        try:
            async with get_session(self.engine) as session:
                now = datetime.now(timezone.utc)

                # 检查超过 30 天无新文章的站点 → priority = 'low'
                result = await session.execute(
                    select(Source)
                    .where(Source.status == 'active')
                    .where(Source.days_without_new >= 30)
                )
                sources_to_low = result.scalars().all()

                for source in sources_to_low:
                    source.priority = 'low'
                    stats["priority_low"] += 1
                    logger.debug(f"Source #{source.id} priority set to low (30+ days without new)")

                # 检查超过 90 天无新文章的站点 → status = 'archived'
                result = await session.execute(
                    select(Source)
                    .where(Source.status.in_(['active', 'degraded']))
                    .where(Source.days_without_new >= 90)
                )
                sources_to_archive = result.scalars().all()

                for source in sources_to_archive:
                    source.status = 'archived'
                    source.archived_at = now
                    stats["archived"] += 1
                    logger.info(f"Source #{source.id} ({source.name}) archived (90+ days without new)")

                await session.commit()

            logger.info(
                f"Daily check completed: {stats['priority_low']} priority low, "
                f"{stats['archived']} archived"
            )

        except Exception as e:
            logger.error(f"Error in daily health check: {e}")

        return stats

    async def run_weekly_probe(self, fetcher) -> Dict[str, int]:
        """
        周检探活：对所有 paused 站点发起 HTTP HEAD 探测。

        参数:
            fetcher: Fetcher 实例

        返回:
            统计信息字典
        """
        stats = {
            "probed": 0,
            "restored": 0,
            "still_paused": 0,
        }

        try:
            async with get_session(self.engine) as session:
                # 获取所有 paused 站点
                result = await session.execute(
                    select(Source).where(Source.status == 'paused')
                )
                paused_sources = result.scalars().all()

                for source in paused_sources:
                    stats["probed"] += 1

                    try:
                        # HTTP HEAD 探测
                        probe_result = await self._probe_source(source, fetcher)

                        if probe_result:
                            # 探测成功，尝试完整抓取一次
                            crawl_result = await self._test_crawl(source, fetcher)

                            if crawl_result:
                                # 恢复为 active
                                source.status = 'active'
                                source.consecutive_errors = 0
                                source.priority = 'medium'
                                source.paused_at = None
                                stats["restored"] += 1
                                logger.info(
                                    f"Source #{source.id} ({source.name}) restored to active"
                                )
                            else:
                                stats["still_paused"] += 1
                        else:
                            stats["still_paused"] += 1

                    except Exception as e:
                        logger.error(f"Error probing source #{source.id}: {e}")
                        stats["still_paused"] += 1

                await session.commit()

            logger.info(
                f"Weekly probe completed: {stats['probed']} probed, "
                f"{stats['restored']} restored, {stats['still_paused']} still paused"
            )

        except Exception as e:
            logger.error(f"Error in weekly probe: {e}")

        return stats

    async def _probe_source(self, source: Source, fetcher) -> bool:
        """
        HTTP HEAD 探测站点。

        返回:
            是否探测成功
        """
        try:
            url = source.url or f"https://{source.domain}"
            result = await fetcher.fetch(url, rendering="static")

            return result.success and result.status_code == 200

        except Exception as e:
            logger.debug(f"Probe failed for {source.domain}: {e}")
            return False

    async def _test_crawl(self, source: Source, fetcher) -> bool:
        """
        测试抓取（简单抓取首页）。

        返回:
            是否抓取成功
        """
        try:
            url = source.url or f"https://{source.domain}"
            result = await fetcher.fetch(url, rendering="static")

            # 检查是否有足够内容
            return result.success and result.content_length > 500

        except Exception as e:
            logger.debug(f"Test crawl failed for {source.domain}: {e}")
            return False

    async def get_sources_needs_repair(self) -> List[Dict]:
        """
        获取需要修复的站点列表（last_error_type = 'extract_empty'）。

        返回:
            站点信息列表
        """
        try:
            async with get_session(self.engine) as session:
                result = await session.execute(
                    select(Source)
                    .where(Source.last_error_type == 'extract_empty')
                    .where(Source.status.in_(['active', 'degraded']))
                    .order_by(Source.consecutive_errors.desc())
                )

                sources = result.scalars().all()

                return [
                    {
                        "id": s.id,
                        "name": s.name,
                        "domain": s.domain,
                        "consecutive_errors": s.consecutive_errors,
                        "last_success_at": s.last_success_at,
                        "last_error": s.last_error,
                    }
                    for s in sources
                ]

        except Exception as e:
            logger.error(f"Error getting sources needing repair: {e}")
            return []

    async def get_health_stats(self) -> Dict:
        """
        获取健康统计信息。

        返回:
            健康统计字典
        """
        try:
            async with get_session(self.engine) as session:
                # 按状态统计
                result = await session.execute(
                    select(
                        Source.status,
                        func.count(Source.id).label('count')
                    )
                    .group_by(Source.status)
                )
                status_counts = {row[0]: row[1] for row in result.fetchall()}

                # 需要修复的站点数
                repair_result = await session.execute(
                    select(func.count(Source.id))
                    .where(Source.last_error_type == 'extract_empty')
                )
                needs_repair = repair_result.scalar() or 0

                return {
                    "active": status_counts.get('active', 0),
                    "degraded": status_counts.get('degraded', 0),
                    "paused": status_counts.get('paused', 0),
                    "archived": status_counts.get('archived', 0),
                    "needs_repair": needs_repair,
                    "total": sum(status_counts.values()),
                }

        except Exception as e:
            logger.error(f"Error getting health stats: {e}")
            return {}


# 全局单例
_health_manager: Optional[HealthManager] = None


def get_health_manager(engine) -> HealthManager:
    """获取全局健康管理器单例"""
    global _health_manager
    if _health_manager is None:
        _health_manager = HealthManager(engine)
    return _health_manager
