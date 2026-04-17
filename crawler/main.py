"""
GlobalAutoNews Crawler - 主入口

启动流程：
1. 初始化数据库连接
2. 初始化 Fetcher, RSSHandler, GenericExtractor, DedupPipeline
3. 启动 APScheduler
4. 注册主调度任务：每 60 秒扫描一次 sources 表
5. 保持运行
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database import get_engine
from crawler.engine.fetcher import Fetcher
from crawler.engine.rss import RSSHandler
from crawler.engine.scheduler import CrawlScheduler
from crawler.extractors.generic import GenericExtractor
from crawler.pipeline.dedup import DedupPipeline

# 日志目录
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "crawler.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(log_file)),
    ],
)
logger = logging.getLogger("crawler")


async def main():
    logger.info("GlobalAutoNews Crawler starting...")
    
    # 从环境变量读取配置
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        sys.exit(1)
    
    max_concurrency = int(os.environ.get("MAX_CONCURRENCY", "5"))
    
    # 初始化数据库连接
    engine = get_engine(database_url)
    logger.info("Database engine initialized")
    
    # 初始化组件
    fetcher = Fetcher()
    rss_handler = RSSHandler(fetcher)
    extractor = GenericExtractor()
    dedup = DedupPipeline()
    
    logger.info("Components initialized")
    
    # 初始化调度器
    scheduler = CrawlScheduler(
        engine=engine,
        fetcher=fetcher,
        rss_handler=rss_handler,
        extractor=extractor,
        dedup=dedup,
        max_concurrency=max_concurrency,
    )
    
    logger.info(f"CrawlScheduler initialized with max_concurrency={max_concurrency}")
    
    # 启动调度循环
    try:
        await scheduler.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    finally:
        # 清理资源
        await fetcher.close()
        await engine.dispose()
        logger.info("Crawler shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())