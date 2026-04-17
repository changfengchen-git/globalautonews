"""
调度引擎

核心类: CrawlScheduler

职责：
1. 定期扫描 sources 表，找出需要抓取的站点
2. 控制并发，按优先级调度
3. 执行抓取→提取→去重→入库的完整流程
4. 更新站点的调度参数和统计信息

实现要求:

=== 主调度循环 ===

1. 每 60 秒执行一次 scan_and_dispatch()
2. 查询：
   ```sql
   SELECT * FROM sources
   WHERE status IN ('active', 'degraded')
   AND next_crawl_at <= NOW()
   ORDER BY
     CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
     next_crawl_at ASC
   LIMIT 20
   ```
3. 对每个站点创建一个异步任务 crawl_source(source)
4. 并发控制：使用 asyncio.Semaphore(MAX_CONCURRENCY)
   - MAX_CONCURRENCY 从环境变量读取，默认 5

=== 单站点抓取流程 crawl_source(source) ===

```
1. 记录 crawl_log 开始时间
2. 获取文章列表 URL：
   - 如果 source.has_rss → 用 RSSHandler.parse_feed() 获取列表
   - 否则 → 用 Fetcher.fetch() 获取列表页 HTML
                → 从 HTML 中提取文章链接（简单的 <a href> 提取）
3. 对每个文章 URL：
   a. DedupPipeline.check_duplicate(url, ...) → L1 URL去重
      - 如果是 L1 重复 → 跳过，不抓取正文
   b. Fetcher.fetch(article_url) → 获取文章页面
   c. GenericExtractor.extract(html, url) → 提取正文
      - 如果 quality_score < 0.5 → 记录日志，跳过该文章
   d. DedupPipeline.check_duplicate(url, title, language) → L2 去重
   e. 创建 Article 对象并保存到数据库
4. 更新 source 记录：
   - last_crawl_at = NOW()
   - last_success_at = NOW()（如果成功）
   - next_crawl_at = NOW() + interval
   - consecutive_errors = 0（如果成功）
   - consecutive_errors += 1（如果失败）
   - 更新 avg_articles_per_crawl
5. 创建 crawl_log 记录
```

=== 文章链接提取（用于非 RSS 站点）===

从列表页 HTML 中提取文章链接：
1. 用 BeautifulSoup 解析 HTML
2. 找所有 <a href="...">
3. 过滤规则：
   - 只保留与当前域名相同的链接
   - 排除导航、分类、标签等非文章页面（URL 中含 /category/, /tag/, /page/, /author/ 等）
   - 排除首页、关于页等（/, /about, /contact, /privacy 等）
   - 保留看起来像文章的 URL：含日期模式 (/2026/04/)、含数字ID、路径深度>=2
4. 去重：去除重复 URL
5. 限制：最多返回 30 个链接

=== 错误处理 ===

- 抓取超时 → 记录 error，跳过该站点
- HTTP 错误 → 记录 error_type='http_error'
- 提取失败 → 记录 error_type='extract_empty'
- 异常 → 记录 error_type='unknown'
- 所有错误都不应该导致调度器崩溃，使用 try/except 包裹每个站点的抓取

=== 并发安全 ===

- 每个站点的抓取在独立的异步任务中
- 数据库操作使用独立的 session（不共享）
- Fetcher 是线程安全的（httpx.AsyncClient 支持并发）
"""
import asyncio
import logging
import os
import hashlib
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.database import get_session
from shared.models import Source, Article, CrawlLog
from crawler.engine.fetcher import Fetcher
from crawler.engine.rss import RSSHandler
from crawler.engine.frequency import FrequencyController
from crawler.engine.health import get_health_manager
from crawler.extractors.generic import GenericExtractor
from crawler.extractors.adapter import get_adapter_extractor, ExtractResult as AdapterExtractResult

# 国家代码到时区的映射（用于计算当地时间）
COUNTRY_TIMEZONE_MAP = {
    # 亚洲
    'CN': 'Asia/Shanghai',  # 中国
    'JP': 'Asia/Tokyo',     # 日本
    'KR': 'Asia/Seoul',     # 韩国
    'IN': 'Asia/Kolkata',   # 印度
    'TH': 'Asia/Bangkok',   # 泰国
    'VN': 'Asia/Ho_Chi_Minh',  # 越南
    'ID': 'Asia/Jakarta',   # 印度尼西亚
    'MY': 'Asia/Kuala_Lumpur',  # 马来西亚
    'PH': 'Asia/Manila',    # 菲律宾
    'SG': 'Asia/Singapore', # 新加坡
    'TW': 'Asia/Taipei',    # 台湾
    'HK': 'Asia/Hong_Kong', # 香港
    
    # 欧洲
    'GB': 'Europe/London',  # 英国
    'DE': 'Europe/Berlin',  # 德国
    'FR': 'Europe/Paris',   # 法国
    'IT': 'Europe/Rome',    # 意大利
    'ES': 'Europe/Madrid',  # 西班牙
    'NL': 'Europe/Amsterdam',  # 荷兰
    'SE': 'Europe/Stockholm',  # 瑞典
    'RU': 'Europe/Moscow',  # 俄罗斯
    
    # 美洲
    'US': 'America/New_York',  # 美国（东部时间）
    'CA': 'America/Toronto',   # 加拿大
    'BR': 'America/Sao_Paulo', # 巴西
    'MX': 'America/Mexico_City',  # 墨西哥
    'AR': 'America/Buenos_Aires',  # 阿根廷
    
    # 大洋洲
    'AU': 'Australia/Sydney',  # 澳大利亚
    'NZ': 'Pacific/Auckland',  # 新西兰
    
    # 中东
    'AE': 'Asia/Dubai',    # 阿联酋
    'SA': 'Asia/Riyadh',   # 沙特阿拉伯
    'IL': 'Asia/Jerusalem',  # 以色列
    'TR': 'Europe/Istanbul',  # 土耳其
}

# 北京时间时区
BEIJING_TZ = timezone(timedelta(hours=8))


def convert_to_three_times(
    published_at: Optional[datetime],
    country: str,
    source_timezone: Optional[str] = None
) -> Tuple[Optional[datetime], Optional[datetime], Optional[datetime]]:
    """
    将发布时间转换为三个时间：本地时间、UTC时间、北京时间
    
    参数:
        published_at: 原始发布时间（可能带时区，也可能不带）
        country: 国家代码（如 'CN', 'US', 'JP'）
        source_timezone: 源时区字符串（可选，优先使用）
    
    返回:
        (published_at_local, published_at_utc, published_at_beijing)
    """
    if published_at is None:
        return None, None, None
    
    # 确定源时区
    source_tz = None
    if source_timezone:
        try:
            from zoneinfo import ZoneInfo
            source_tz = ZoneInfo(source_timezone)
        except Exception:
            pass
    
    if source_tz is None and country in COUNTRY_TIMEZONE_MAP:
        try:
            from zoneinfo import ZoneInfo
            source_tz = ZoneInfo(COUNTRY_TIMEZONE_MAP[country])
        except Exception:
            pass
    
    # 如果原始时间没有时区信息，假设它是源时区的时间
    if published_at.tzinfo is None:
        if source_tz:
            published_at = published_at.replace(tzinfo=source_tz)
        else:
            # 默认假设为UTC
            published_at = published_at.replace(tzinfo=timezone.utc)
    
    # 1. 本地时间（保留原始时区信息）
    published_at_local = published_at
    
    # 2. UTC时间
    published_at_utc = published_at.astimezone(timezone.utc)
    
    # 3. 北京时间
    published_at_beijing = published_at.astimezone(BEIJING_TZ)
    
    return published_at_local, published_at_utc, published_at_beijing
from crawler.pipeline.dedup import DedupPipeline
from crawler.pipeline.clustering import get_cluster_manager

logger = logging.getLogger("crawler.scheduler")


class CrawlScheduler:
    def __init__(
        self,
        engine: AsyncEngine,
        fetcher: Fetcher,
        rss_handler: RSSHandler,
        extractor: GenericExtractor,
        dedup: DedupPipeline,
        max_concurrency: int = 5,
    ):
        self.engine = engine
        self.fetcher = fetcher
        self.rss_handler = rss_handler
        self.extractor = extractor
        self.dedup = dedup
        self.frequency_controller = FrequencyController()
        self.health_manager = get_health_manager(engine)
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def start(self):
        """启动调度循环"""
        logger.info("CrawlScheduler started")
        while True:
            try:
                await self.scan_and_dispatch()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            await asyncio.sleep(60)

    async def scan_and_dispatch(self):
        """扫描到期的站点并分发抓取任务"""
        logger.info("Scanning for sources due for crawl...")
        
        async with get_session(self.engine) as session:
            # 查询需要抓取的站点
            query = text("""
                SELECT id FROM sources
                WHERE status IN ('active', 'degraded')
                AND next_crawl_at <= NOW()
                ORDER BY
                    CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                    next_crawl_at ASC
                LIMIT 20
            """)
            
            result = await session.execute(query)
            source_ids = [row[0] for row in result.fetchall()]
            
            if not source_ids:
                logger.debug("No sources due for crawl")
                return
            
            logger.info(f"Found {len(source_ids)} sources to crawl")
            
            # 创建抓取任务
            tasks = []
            for source_id in source_ids:
                task = asyncio.create_task(self.crawl_source(source_id))
                tasks.append(task)
            
            # 等待所有任务完成
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.info(f"Completed crawling {len(tasks)} sources")

    async def crawl_source(self, source_id: int):
        """抓取单个站点的完整流程"""
        async with self.semaphore:
            started_at = datetime.now(timezone.utc)
            
            try:
                async with get_session(self.engine) as session:
                    # 获取 source 记录
                    result = await session.execute(
                        select(Source).where(Source.id == source_id)
                    )
                    source = result.scalar_one_or_none()
                    
                    if not source:
                        logger.warning(f"Source {source_id} not found")
                        return
                    
                    logger.info(f"Crawling source #{source.id}: {source.name} ({source.domain})")
                    
                    # 根据是否有 RSS 选择抓取方式
                    if source.has_rss and source.rss_url:
                        articles_found, articles_new, articles_duplicate = await self._crawl_via_rss(source, session)
                    else:
                        articles_found, articles_new, articles_duplicate = await self._crawl_via_html(source, session)
                    
                    # 更新 source 记录
                    await self._update_source_success(source, articles_found, articles_new, session)
                    
                    # 创建 crawl_log 记录
                    await self._create_crawl_log(
                        source_id=source.id,
                        started_at=started_at,
                        status="success",
                        tier_used=source.tier,
                        articles_found=articles_found,
                        articles_new=articles_new,
                        articles_duplicate=articles_duplicate,
                        completed_at=datetime.now(timezone.utc)
                    )
                    
                    logger.info(f"Source #{source.id} crawled: {articles_found} found, {articles_new} new")
                    
            except Exception as e:
                logger.error(f"Error crawling source {source_id}: {e}")
                
                # 记录错误
                try:
                    async with get_session(self.engine) as session:
                        result = await session.execute(
                            select(Source).where(Source.id == source_id)
                        )
                        source = result.scalar_one_or_none()
                        if source:
                            await self._update_source_error(source, "unknown", str(e), session)
                            await self._create_crawl_log(
                                source_id=source_id,
                                started_at=started_at,
                                status="error",
                                error_message=str(e),
                                completed_at=datetime.now(timezone.utc)
                            )
                except Exception as log_error:
                    logger.error(f"Error logging crawl failure: {log_error}")

    def _get_crawl_time_threshold(self, source: Source) -> Optional[datetime]:
        """
        获取抓取时间阈值，用于增量抓取
        
        - 首次抓取 (last_crawl_at 为 None): 只抓取最近 30 天的内容
        - 后续抓取: 只抓取比 last_crawl_at 更新的内容
        """
        now = datetime.now(timezone.utc)
        
        if source.last_crawl_at is None:
            # 首次抓取，只抓取最近 30 天
            threshold = now - timedelta(days=30)
            logger.debug(f"First crawl for {source.name}, threshold: {threshold}")
        else:
            # 后续抓取，只抓取比上次抓取时间新的内容
            # 额外留 1 小时余量，防止漏掉边界内容
            threshold = source.last_crawl_at - timedelta(hours=1)
            logger.debug(f"Incremental crawl for {source.name}, threshold: {threshold}")
        
        return threshold

    def _is_article_within_time_range(self, published_at: Optional[datetime], threshold: Optional[datetime]) -> bool:
        """检查文章是否在时间范围内"""
        if threshold is None:
            return True
        
        if published_at is None:
            # 没有发布时间的文章，允许抓取（可能是新文章）
            return True
        
        # 确保两个时间都是 timezone-aware
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        
        return published_at >= threshold

    async def _crawl_via_rss(self, source: Source, session) -> Tuple[int, int, int]:
        """通过 RSS 抓取文章列表并处理每篇文章"""
        articles_found = 0
        articles_new = 0
        articles_duplicate = 0
        articles_skipped = 0
        
        try:
            # 获取时间阈值
            time_threshold = self._get_crawl_time_threshold(source)
            
            # 解析 RSS
            feed_items = await self.rss_handler.parse_feed(source.rss_url)
            
            # 过滤时间范围内的文章
            filtered_items = []
            for item in feed_items:
                if self._is_article_within_time_range(item.published_at, time_threshold):
                    filtered_items.append(item)
                else:
                    articles_skipped += 1
            
            articles_found = len(filtered_items)
            
            logger.debug(f"RSS feed for {source.name}: {len(feed_items)} items, {articles_found} within time range, {articles_skipped} skipped")
            
            # 处理每篇文章
            for item in filtered_items[:30]:  # 限制最多 30 篇
                if not item.url:
                    continue
                
                status = await self._process_article(item.url, source, session, time_threshold)
                
                if status == "new":
                    articles_new += 1
                elif status == "duplicate":
                    articles_duplicate += 1
            
        except Exception as e:
            logger.error(f"Error crawling via RSS for {source.name}: {e}")
        
        return articles_found, articles_new, articles_duplicate

    async def _crawl_via_html(self, source: Source, session) -> Tuple[int, int, int]:
        """通过列表页 HTML 抓取文章链接并处理"""
        articles_found = 0
        articles_new = 0
        articles_duplicate = 0
        
        try:
            # 获取时间阈值
            time_threshold = self._get_crawl_time_threshold(source)
            
            # 获取列表页 HTML
            result = await self.fetcher.fetch(source.url, rendering="static")
            
            if not result.success or not result.html:
                logger.warning(f"Failed to fetch list page for {source.name}")
                return articles_found, articles_new, articles_duplicate
            
            # 提取文章链接
            article_urls = self._extract_article_links(result.html, source.url, source.domain)
            articles_found = len(article_urls)
            
            logger.debug(f"HTML list for {source.name}: {articles_found} article URLs")
            
            # 处理每篇文章
            for article_url in article_urls[:30]:  # 限制最多 30 篇
                status = await self._process_article(article_url, source, session, time_threshold)
                
                if status == "new":
                    articles_new += 1
                elif status == "duplicate":
                    articles_duplicate += 1
            
        except Exception as e:
            logger.error(f"Error crawling via HTML for {source.name}: {e}")
        
        return articles_found, articles_new, articles_duplicate

    async def _process_article(
        self, 
        article_url: str, 
        source: Source, 
        session,
        time_threshold: Optional[datetime] = None
    ) -> str:
        """
        处理单篇文章：抓取→提取→去重→聚类→入库
        返回: "new" | "duplicate" | "failed" | "skipped"
        """
        try:
            # L1: URL 去重检查
            dedup_result = await self.dedup.check_duplicate(
                url=article_url,
                title="",  # L1 不需要标题
                language="",
                session=session
            )
            
            if dedup_result.is_duplicate and dedup_result.dedup_level == 1:
                logger.debug(f"L1 duplicate: {article_url}")
                return "duplicate"
            
            # 抓取文章页面
            fetch_result = await self.fetcher.fetch(article_url, rendering="static")
            
            if not fetch_result.success or not fetch_result.html:
                logger.debug(f"Failed to fetch article: {article_url}")
                return "failed"
            
            # 提取正文（根据 Tier 选择提取器）
            adapter_extractor = get_adapter_extractor()
            
            if source.tier == 2 and adapter_extractor.has_adapter(source.domain):
                # Tier 2: 使用适配器
                adapter_result = adapter_extractor.extract_article(
                    fetch_result.html, fetch_result.url, source.domain
                )
                if adapter_result.success:
                    # 转换为通用格式
                    extract_result = type('obj', (object,), {
                        'success': True,
                        'title': adapter_result.title,
                        'content': adapter_result.content,
                        'content_length': adapter_result.content_length,
                        'excerpt': adapter_result.content[:200] if adapter_result.content else '',
                        'author': adapter_result.author,
                        'image_url': adapter_result.image_url,
                        'image_urls': adapter_result.image_urls,
                        'language': adapter_result.language,
                        'published_at': adapter_result.published_at,
                        'external_links': [],
                        'quality_score': 1.0,
                    })()
                else:
                    # 适配器失败，回退到通用提取器
                    extract_result = self.extractor.extract(fetch_result.html, fetch_result.url)
            else:
                # Tier 1: 使用通用提取器
                extract_result = self.extractor.extract(fetch_result.html, fetch_result.url)
            
            if not extract_result.success or extract_result.quality_score < 0.5:
                logger.debug(f"Low quality extraction: {article_url} (score: {extract_result.quality_score})")
                return "skipped"
            
            # 增量抓取：检查文章发布时间是否在时间范围内
            if time_threshold and not self._is_article_within_time_range(extract_result.published_at, time_threshold):
                logger.debug(f"Article too old: {article_url} (published: {extract_result.published_at}, threshold: {time_threshold})")
                return "skipped"
            
            # L2-L4: 完整去重检查（包括标题、实体、嵌入）
            dedup_result = await self.dedup.check_duplicate(
                url=article_url,
                title=extract_result.title or "",
                language=extract_result.language or "en",
                session=session,
                content=extract_result.content or ""
            )
            
            if dedup_result.is_duplicate:
                logger.debug(f"L{dedup_result.dedup_level} duplicate: {article_url}")
                
                # 计算三个时间
                published_at_local, published_at_utc, published_at_beijing = convert_to_three_times(
                    extract_result.published_at,
                    source.country
                )
                
                # 即使是重复文章，也创建记录并关联到 event_cluster
                article = Article(
                    source_id=source.id,
                    url=fetch_result.url,
                    url_hash=DedupPipeline.hash_url(article_url),
                    title=extract_result.title or "",
                    title_simhash=DedupPipeline.compute_simhash(
                        extract_result.title or "",
                        extract_result.language or "en"
                    ),
                    content=extract_result.content,
                    content_length=extract_result.content_length,
                    excerpt=extract_result.excerpt,
                    author=extract_result.author,
                    image_url=extract_result.image_url,
                    image_urls=extract_result.image_urls,
                    language=extract_result.language or source.language,
                    country=source.country,
                    published_at=published_at_utc,
                    published_at_local=published_at_local,
                    published_at_beijing=published_at_beijing,
                    external_links=extract_result.external_links,
                    is_duplicate=True,
                    dedup_level=dedup_result.dedup_level,
                )
                
                session.add(article)
                await session.flush()
                
                # 聚类到 event_cluster
                cluster_manager = get_cluster_manager()
                await cluster_manager.cluster_article(
                    article, session, duplicate_of=dedup_result.duplicate_of
                )
                
                return "duplicate"
            
            # 计算三个时间
            published_at_local, published_at_utc, published_at_beijing = convert_to_three_times(
                extract_result.published_at,
                source.country
            )
            
            # 创建 Article 对象并保存
            article = Article(
                source_id=source.id,
                url=fetch_result.url,
                url_hash=DedupPipeline.hash_url(article_url),
                title=extract_result.title or "",
                title_simhash=DedupPipeline.compute_simhash(
                    extract_result.title or "",
                    extract_result.language or "en"
                ),
                content=extract_result.content,
                content_length=extract_result.content_length,
                excerpt=extract_result.excerpt,
                author=extract_result.author,
                image_url=extract_result.image_url,
                image_urls=extract_result.image_urls,
                language=extract_result.language or source.language,
                country=source.country,
                published_at=published_at_utc,
                published_at_local=published_at_local,
                published_at_beijing=published_at_beijing,
                external_links=extract_result.external_links,
                is_duplicate=False,
                dedup_level=None,
            )
            
            session.add(article)
            await session.flush()  # 获取 article.id
            
            # 创建新的 event_cluster
            cluster_manager = get_cluster_manager()
            await cluster_manager.cluster_article(article, session)
            
            logger.debug(f"New article saved: {article_url}")
            return "new"
            
        except Exception as e:
            logger.error(f"Error processing article {article_url}: {e}")
            return "failed"

    def _extract_article_links(self, html: str, base_url: str, domain: str) -> List[str]:
        """从列表页 HTML 中提取文章链接"""
        article_urls = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            a_tags = soup.find_all('a', href=True)
            
            base_domain = urlparse(base_url).netloc.lower()
            if base_domain.startswith('www.'):
                base_domain = base_domain[4:]
            
            # 排除的路径模式
            exclude_patterns = [
                '/category/', '/tag/', '/page/', '/author/',
                '/about', '/contact', '/privacy', '/terms',
                '/login', '/signup', '/register', '/account',
                '/search', '/archive', '/sitemap',
            ]
            
            for a in a_tags:
                href = a['href']
                
                # 转换为绝对 URL
                if not href.startswith(('http://', 'https://')):
                    href = urljoin(base_url, href)
                
                # 解析域名
                try:
                    link_domain = urlparse(href).netloc.lower()
                    if link_domain.startswith('www.'):
                        link_domain = link_domain[4:]
                except Exception:
                    continue
                
                # 只保留同域名链接
                if link_domain != base_domain:
                    continue
                
                # 排除非文章页面
                path = urlparse(href).path.lower()
                
                # 排除首页
                if path in ['/', '']:
                    continue
                
                # 排除排除列表中的路径
                if any(pattern in path for pattern in exclude_patterns):
                    continue
                
                # 检查是否是文章 URL
                if self._is_article_url(href):
                    article_urls.append(href)
            
            # 去重
            article_urls = list(dict.fromkeys(article_urls))
            
            # 限制数量
            article_urls = article_urls[:30]
            
        except Exception as e:
            logger.debug(f"Error extracting article links: {e}")
        
        return article_urls

    def _is_article_url(self, url: str) -> bool:
        """判断 URL 是否是文章页面"""
        path = urlparse(url).path.lower()
        
        # 包含日期模式
        import re
        date_patterns = [
            r'/\d{4}/\d{2}/',  # /2026/04/
            r'/\d{4}-\d{2}-\d{2}/',  # /2026-04-15/
        ]
        
        for pattern in date_patterns:
            if re.search(pattern, path):
                return True
        
        # 路径深度 >= 2
        path_parts = [p for p in path.split('/') if p]
        if len(path_parts) >= 2:
            # 最后一部分看起来像文章标题（包含连字符或下划线）
            last_part = path_parts[-1]
            if '-' in last_part or '_' in last_part:
                return True
        
        # 包含数字 ID
        if re.search(r'/\d{4,}', path):
            return True
        
        return False

    async def _update_source_success(self, source: Source, articles_found: int, articles_new: int, session):
        """成功后更新 source 记录（使用自适应调频和健康管理）"""
        try:
            now = datetime.now(timezone.utc)
            
            # 使用健康管理器更新状态
            self.health_manager.update_health_after_crawl(
                source=source,
                success=True,
                articles_new=articles_new
            )
            
            source.last_crawl_at = now
            
            # 使用频率控制器计算新的抓取间隔
            current_interval = source.crawl_interval_minutes or 240
            current_avg = source.avg_articles_per_crawl or 0
            crawl_count = source.crawl_count or 0
            
            # 获取本次抓取的文章发布时间（用于发布模式分析）
            publish_times = []
            # 这里可以从抓取的文章中获取发布时间，暂时为空
            
            # 使用频率控制器更新频率
            freq_result = self.frequency_controller.update_source_frequency(
                current_interval=current_interval,
                articles_new=articles_new,
                articles_found=articles_found,
                current_avg=current_avg,
                crawl_count=crawl_count,
                publish_times=publish_times
            )
            
            # 更新 source 记录
            source.crawl_interval_minutes = freq_result["crawl_interval_minutes"]
            source.next_crawl_at = freq_result["next_crawl_at"]
            source.discovery_rate = freq_result["discovery_rate"]
            source.avg_articles_per_crawl = freq_result["avg_articles_per_crawl"]
            source.crawl_count = crawl_count + 1
            
            # 更新发布时间统计（用于 Phase 5 的 T5.02）
            source.publish_hours = freq_result["publish_hours"]
            source.publish_weekdays = freq_result["publish_weekdays"]
            
            await session.flush()
            
            logger.debug(f"Source #{source.id} frequency updated: interval={source.crawl_interval_minutes}min, "
                        f"discovery_rate={source.discovery_rate:.2f}, avg_articles={source.avg_articles_per_crawl:.1f}")
            
        except Exception as e:
            logger.error(f"Error updating source success: {e}")

    async def _update_source_error(self, source: Source, error_type: str, error_msg: str, session):
        """失败后更新 source 记录（使用健康管理器）"""
        try:
            now = datetime.now(timezone.utc)
            
            # 使用健康管理器更新状态
            self.health_manager.update_health_after_crawl(
                source=source,
                success=False,
                error_type=error_type
            )
            
            source.last_crawl_at = now
            source.last_error = error_msg[:500]  # 限制长度
            
            # 计算下次抓取时间（指数退避）
            base_interval = source.crawl_interval_minutes or 240
            backoff_factor = min(source.consecutive_errors, 10)
            next_interval = base_interval * (2 ** backoff_factor)
            source.next_crawl_at = now + timedelta(minutes=next_interval)
            
            await session.flush()
            
        except Exception as e:
            logger.error(f"Error updating source error: {e}")

    async def _create_crawl_log(self, source_id: int, started_at: datetime, status: str, **kwargs):
        """创建抓取日志"""
        try:
            async with get_session(self.engine) as session:
                log = CrawlLog(
                    source_id=source_id,
                    started_at=started_at,
                    completed_at=kwargs.get('completed_at'),
                    status=status,
                    tier_used=kwargs.get('tier_used'),
                    articles_found=kwargs.get('articles_found', 0),
                    articles_new=kwargs.get('articles_new', 0),
                    articles_duplicate=kwargs.get('articles_duplicate', 0),
                    response_time_ms=kwargs.get('response_time_ms'),
                    error_message=kwargs.get('error_message'),
                )
                session.add(log)
                await session.commit()
                
        except Exception as e:
            logger.error(f"Error creating crawl log: {e}")