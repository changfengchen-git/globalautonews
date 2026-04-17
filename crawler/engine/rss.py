"""
RSS 探测与解析器

核心类: RSSHandler

公开方法:
    async def detect_rss(domain: str, base_url: str) -> str | None
    async def parse_feed(rss_url: str) -> list[FeedItem]

FeedItem 数据类:
    title: str               # 文章标题
    url: str                 # 文章链接
    published_at: datetime | None  # 发布时间
    author: str | None       # 作者
    summary: str | None      # 摘要

实现要求:

1. RSS 探测逻辑 (detect_rss):
   按顺序尝试以下常见 RSS 路径，第一个成功返回有效 RSS 内容的即为结果：
   - {base_url}/feed
   - {base_url}/feed/
   - {base_url}/rss
   - {base_url}/rss/
   - {base_url}/atom.xml
   - {base_url}/rss.xml
   - {base_url}/feed.xml
   - {base_url}/index.xml
   - https://{domain}/feed
   - https://{domain}/rss

   检测方法：
   - 发送 HEAD 请求（超时 10 秒）
   - 检查 Content-Type 是否包含 'xml', 'rss', 'atom'
   - 如果 HEAD 不支持，发送 GET 请求，检查内容开头是否为 XML

   另外也检查 HTML 页面中的 <link rel="alternate" type="application/rss+xml">
   - 从 base_url 的 HTML 中用正则提取 RSS link 标签

2. RSS 解析逻辑 (parse_feed):
   - 使用 feedparser 库解析 RSS/Atom 内容
   - 提取每篇文章的 title, link, published, author, summary
   - 处理发布时间的多种格式（RFC 822, ISO 8601, 等）
   - 返回 FeedItem 列表，按发布时间倒序排列
   - 最多返回 50 条

3. 错误处理：
   - 解析失败返回空列表
   - 探测失败返回 None
"""
import re
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from urllib.parse import urljoin

import feedparser

from crawler.engine.fetcher import Fetcher

logger = logging.getLogger("crawler.rss")


@dataclass
class FeedItem:
    title: str
    url: str
    published_at: Optional[datetime] = None
    author: Optional[str] = None
    summary: Optional[str] = None


class RSSHandler:
    RSS_PATHS = [
        "/feed", "/feed/", "/rss", "/rss/",
        "/atom.xml", "/rss.xml", "/feed.xml", "/index.xml",
    ]

    def __init__(self, fetcher: Fetcher):
        self.fetcher = fetcher

    async def detect_rss(self, domain: str, base_url: str) -> Optional[str]:
        """
        自动探测站点的 RSS 订阅源 URL。
        
        返回:
            RSS URL 字符串，未找到返回 None
        """
        logger.info(f"Detecting RSS for {domain} (base: {base_url})")
        
        # 1. 尝试常见 RSS 路径
        for path in self.RSS_PATHS:
            # 相对于 base_url 的路径
            candidate_url = urljoin(base_url, path)
            if await self._check_rss_url(candidate_url):
                logger.info(f"Found RSS at {candidate_url}")
                return candidate_url
        
        # 2. 尝试域名根目录的路径
        domain_root = f"https://{domain}"
        for path in ["/feed", "/rss"]:
            candidate_url = domain_root + path
            if await self._check_rss_url(candidate_url):
                logger.info(f"Found RSS at {candidate_url}")
                return candidate_url
        
        # 3. 从 HTML 页面中提取 RSS link 标签
        rss_url = await self._extract_rss_from_html_page(base_url)
        if rss_url:
            logger.info(f"Found RSS in HTML: {rss_url}")
            return rss_url
        
        logger.debug(f"No RSS found for {domain}")
        return None

    async def _check_rss_url(self, url: str) -> bool:
        """检查给定 URL 是否是有效的 RSS 源"""
        try:
            # 首先尝试 HEAD 请求
            result = await self.fetcher.fetch(url, rendering="static")
            
            # 检查 Content-Type
            content_type = ""
            # 注意：FetchResult 没有 headers，我们需要修改 Fetcher 来保存 headers
            # 暂时使用 GET 请求来检查内容
            if result.success and result.html:
                # 检查内容是否是 XML/RSS
                content = result.html.strip()
                if content.startswith("<?xml") or content.startswith("<rss") or content.startswith("<feed"):
                    # 进一步用 feedparser 验证
                    try:
                        feed = feedparser.parse(content)
                        if feed.entries:
                            return True
                    except Exception:
                        pass
            
            return False
            
        except Exception as e:
            logger.debug(f"Error checking RSS at {url}: {e}")
            return False

    async def _extract_rss_from_html_page(self, url: str) -> Optional[str]:
        """从 HTML 页面中提取 RSS link 标签"""
        try:
            result = await self.fetcher.fetch(url, rendering="static")
            if not result.success or not result.html:
                return None
            
            return self._extract_rss_from_html(result.html, url)
            
        except Exception as e:
            logger.debug(f"Error fetching HTML for RSS extraction: {e}")
            return None

    def _extract_rss_from_html(self, html: str, base_url: str) -> Optional[str]:
        """
        从 HTML 中提取 <link rel="alternate" type="application/rss+xml"> 标签
        """
        # 匹配 RSS link 标签
        patterns = [
            r'<link[^>]+rel=["\']alternate["\'][^>]+type=["\']application/rss\+xml["\'][^>]+href=["\']([^"\']+)["\']',
            r'<link[^>]+type=["\']application/rss\+xml["\'][^>]+rel=["\']alternate["\'][^>]+href=["\']([^"\']+)["\']',
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]+type=["\']application/rss\+xml["\']',
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\']alternate["\'][^>]+type=["\']application/rss\+xml["\']',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                # 返回第一个匹配的 URL
                rss_url = matches[0]
                # 如果是相对路径，转换为绝对路径
                if not rss_url.startswith(('http://', 'https://')):
                    rss_url = urljoin(base_url, rss_url)
                return rss_url
        
        return None

    async def parse_feed(self, rss_url: str) -> list[FeedItem]:
        """
        解析 RSS 订阅源，返回文章列表。
        
        返回:
            FeedItem 列表（最多 50 条，按时间倒序）
        """
        try:
            # 获取 RSS 内容
            result = await self.fetcher.fetch(rss_url, rendering="static")
            if not result.success or not result.html:
                logger.warning(f"Failed to fetch RSS: {rss_url}")
                return []
            
            # 使用 feedparser 解析
            feed = feedparser.parse(result.html)
            
            if feed.bozo and not feed.entries:
                logger.warning(f"Failed to parse RSS feed: {rss_url}")
                return []
            
            items = []
            for entry in feed.entries[:50]:  # 最多 50 条
                # 提取发布时间
                published_at = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_at = self._parse_datetime(entry.published_parsed)
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    published_at = self._parse_datetime(entry.updated_parsed)
                
                # 提取摘要
                summary = None
                if hasattr(entry, 'summary'):
                    summary = entry.summary
                elif hasattr(entry, 'description'):
                    summary = entry.description
                
                item = FeedItem(
                    title=entry.get('title', 'Untitled'),
                    url=entry.get('link', ''),
                    published_at=published_at,
                    author=entry.get('author'),
                    summary=summary,
                )
                items.append(item)
            
            # 按发布时间倒序排列
            items.sort(key=lambda x: x.published_at or datetime.min, reverse=True)
            
            logger.info(f"Parsed {len(items)} items from {rss_url}")
            return items
            
        except Exception as e:
            logger.error(f"Error parsing RSS feed {rss_url}: {e}")
            return []

    def _parse_datetime(self, time_struct) -> Optional[datetime]:
        """将 feedparser 的 time_struct 转为 datetime"""
        try:
            from datetime import timezone
            return datetime(*time_struct[:6], tzinfo=timezone.utc)
        except Exception:
            return None