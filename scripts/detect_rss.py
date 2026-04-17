"""
批量 RSS 探测脚本

用法：
    python scripts/detect_rss.py

功能：
    1. 从数据库读取所有 sources（status='active'）
    2. 对每个 source 执行 RSS 探测
    3. 发现 RSS 后更新 source 记录：
       - has_rss = True
       - rss_url = 探测到的 URL
    4. 输出统计：发现 RSS 的站点数 / 总站点数

注意：
    - 并发控制：最多 10 个并发探测
    - 每个站点探测超时 30 秒
    - 探测结果持久化到数据库
"""
import asyncio
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database import get_engine, get_session
from shared.models import Source
from crawler.engine.fetcher import Fetcher
from crawler.engine.rss import RSSHandler
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("scripts.detect_rss")


async def detect_rss_for_source(
    source: Source,
    rss_handler: RSSHandler,
    semaphore: asyncio.Semaphore,
) -> bool:
    """为单个 source 探测 RSS"""
    async with semaphore:
        try:
            logger.info(f"Detecting RSS for {source.name} ({source.url})")
            
            # 使用 asyncio.wait_for 设置超时
            try:
                rss_url = await asyncio.wait_for(
                    rss_handler.detect_rss(source.domain, source.url),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"RSS detection timeout for {source.name}")
                return False
            
            if rss_url:
                logger.info(f"Found RSS for {source.name}: {rss_url}")
                return True
            else:
                logger.debug(f"No RSS found for {source.name}")
                return False
                
        except Exception as e:
            logger.error(f"Error detecting RSS for {source.name}: {e}")
            return False


async def update_source_rss(
    session,
    source_id: int,
    rss_url: str,
) -> None:
    """更新 source 的 RSS 信息"""
    result = await session.execute(
        select(Source).where(Source.id == source_id)
    )
    source = result.scalar_one_or_none()
    
    if source:
        source.has_rss = True
        source.rss_url = rss_url
        # 更新时间戳
        source.updated_at = datetime.now(timezone.utc)


async def main():
    logger.info("Starting RSS detection script")
    
    # 初始化数据库连接
    engine = get_engine()
    
    # 初始化 Fetcher 和 RSSHandler
    fetcher = Fetcher()
    rss_handler = RSSHandler(fetcher)
    
    # 并发控制：最多 10 个并发探测
    semaphore = asyncio.Semaphore(10)
    
    async with get_session(engine) as session:
        # 读取所有 active 状态的 sources
        result = await session.execute(
            select(Source).where(Source.status == 'active')
        )
        sources = result.scalars().all()
        
        total = len(sources)
        logger.info(f"Found {total} active sources")
        
        if total == 0:
            logger.info("No active sources to process")
            return
        
        # 创建探测任务
        tasks = []
        for source in sources:
            task = detect_rss_for_source(source, rss_handler, semaphore)
            tasks.append((source, task))
        
        # 并发执行探测
        results = await asyncio.gather(
            *[task for _, task in tasks],
            return_exceptions=True
        )
        
        # 统计结果并更新数据库
        found_count = 0
        for i, (source, _) in enumerate(tasks):
            if isinstance(results[i], Exception):
                logger.error(f"Task failed for {source.name}: {results[i]}")
                continue
            
            if results[i]:  # 找到了 RSS
                # 需要重新获取 rss_url，因为 detect_rss_for_source 只返回 bool
                # 我们需要重新调用 detect_rss 来获取 URL
                try:
                    rss_url = await asyncio.wait_for(
                        rss_handler.detect_rss(source.domain, source.url),
                        timeout=30.0
                    )
                    if rss_url:
                        await update_source_rss(session, source.id, rss_url)
                        found_count += 1
                except Exception as e:
                    logger.error(f"Error getting RSS URL for {source.name}: {e}")
        
        # 提交事务
        await session.commit()
        
        logger.info(f"RSS detection complete: {found_count}/{total} sources have RSS")
    
    # 清理资源
    await fetcher.close()
    await engine.dispose()
    
    logger.info("Script finished")


if __name__ == "__main__":
    asyncio.run(main())