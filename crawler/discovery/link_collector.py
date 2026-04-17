"""
外链收集器

从已抓文章的 external_links 中收集候选新信息源。

功能：
1. 扫描最近 24h 内新入库文章的 external_links
2. 提取域名，过滤黑名单域名
3. 保留包含汽车关键词的 URL
4. 更新 source_candidates 表
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Set, Dict, Optional
from urllib.parse import urlparse
from collections import defaultdict

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from shared.models import Article, Source, SourceCandidate

logger = logging.getLogger("crawler.discovery.link_collector")


# 多语言汽车关键词
AUTO_KEYWORDS = {
    "auto", "car", "motor", "vehicle", "ev", "electric",
    "automobile", "automotive", "otomotif", "voiture",
    "carro", "coche", "wagen", "kuruma", "xe", "mobil",
    "news", "review", "drive", "speed", "racing", "f1", "formula",
    "tesla", "byd", "nio", "toyota", "honda", "bmw", "mercedes",
}

# 黑名单域名（社交媒体、搜索引擎、CDN 等）
BLACKLIST_DOMAINS = {
    # 社交媒体
    "facebook.com", "fb.com", "twitter.com", "x.com", "instagram.com",
    "linkedin.com", "youtube.com", "tiktok.com", "reddit.com",
    "pinterest.com", "tumblr.com", "weibo.com", "weixin.qq.com",
    
    # 搜索引擎
    "google.com", "google.co.uk", "baidu.com", "bing.com",
    "yahoo.com", "yandex.com", "duckduckgo.com",
    
    # CDN/托管
    "cloudflare.com", "amazonaws.com", "cloud.google.com",
    "azure.com", "akamai.com", "fastly.com",
    
    # 通用/工具
    "wikipedia.org", "github.com", "stackoverflow.com",
    "medium.com", "substack.com",
    
    # 广告/追踪
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "facebook.net", "analytics.google.com",
    
    # 图片/媒体托管
    "imgur.com", "flickr.com", "unsplash.com", "pexels.com",
    
    # 其他非新闻站点
    "wordpress.com", "blogspot.com", "wix.com", "squarespace.com",
}

# 已知的汽车新闻域名（用于过滤）
KNOWN_AUTOMOTIVE_DOMAINS = {
    "autoblog.com", "motor1.com", "caranddriver.com", "motortrend.com",
    "edmunds.com", "jalopnik.com", "thetruthaboutcars.com", "autoweek.com",
    "topgear.com", "autoexpress.co.uk", "carwow.co.uk",
}


class LinkCollector:
    """外链收集器"""

    def __init__(self, engine):
        """
        初始化外链收集器。

        参数:
            engine: SQLAlchemy async engine
        """
        self.engine = engine

    async def collect(self, hours: int = 24) -> Dict[str, int]:
        """
        收集最近指定小时数内文章的外链。

        参数:
            hours: 扫描最近多少小时的文章

        返回:
            统计信息字典
        """
        stats = {
            "articles_scanned": 0,
            "links_found": 0,
            "candidates_created": 0,
            "candidates_updated": 0,
            "links_filtered": 0,
        }

        try:
            # 获取最近的文章
            articles = await self._get_recent_articles(hours)
            stats["articles_scanned"] = len(articles)

            # 收集所有外链
            domain_links: Dict[str, List[Dict]] = defaultdict(list)

            for article in articles:
                if not article.external_links:
                    continue

                for link_info in article.external_links:
                    if not isinstance(link_info, dict):
                        continue

                    url = link_info.get("url", "")
                    if not url:
                        continue

                    stats["links_found"] += 1

                    # 提取域名
                    domain = self._extract_domain(url)
                    if not domain:
                        continue

                    # 过滤黑名单
                    if self._is_blacklisted(domain):
                        stats["links_filtered"] += 1
                        continue

                    # 检查是否包含汽车关键词
                    if not self._has_automotive_keywords(url):
                        stats["links_filtered"] += 1
                        continue

                    # 添加到收集列表
                    domain_links[domain].append({
                        "url": url,
                        "anchor": link_info.get("anchor", ""),
                        "article_id": article.id,
                        "article_title": article.title,
                    })

            # 更新 source_candidates 表
            async with get_session(self.engine) as session:
                for domain, links in domain_links.items():
                    result = await self._update_or_create_candidate(
                        session, domain, links
                    )
                    if result == "created":
                        stats["candidates_created"] += 1
                    elif result == "updated":
                        stats["candidates_updated"] += 1

                await session.commit()

            logger.info(
                f"Link collection completed: {stats['articles_scanned']} articles, "
                f"{stats['candidates_created']} new candidates, "
                f"{stats['candidates_updated']} updated"
            )

        except Exception as e:
            logger.error(f"Error in link collection: {e}")

        return stats

    async def _get_recent_articles(self, hours: int) -> List[Article]:
        """获取最近指定小时数内的文章"""
        try:
            async with get_session(self.engine) as session:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

                result = await session.execute(
                    select(Article)
                    .where(Article.crawled_at >= cutoff_time)
                    .where(Article.external_links.isnot(None))
                    .order_by(Article.crawled_at.desc())
                )

                return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Error fetching recent articles: {e}")
            return []

    def _extract_domain(self, url: str) -> Optional[str]:
        """从 URL 提取域名"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # 移除 www. 前缀
            if domain.startswith("www."):
                domain = domain[4:]

            # 移除端口号
            if ":" in domain:
                domain = domain.split(":")[0]

            return domain if domain else None

        except Exception:
            return None

    def _is_blacklisted(self, domain: str) -> bool:
        """检查域名是否在黑名单中"""
        # 精确匹配
        if domain in BLACKLIST_DOMAINS:
            return True

        # 检查是否是已知汽车新闻站点（不过滤）
        if domain in KNOWN_AUTOMOTIVE_DOMAINS:
            return False

        # 检查是否是已有的 source 域名
        # 这里需要查询数据库，但为了性能，我们先跳过
        # 在 _update_or_create_candidate 中会检查

        # 检查子域名模式
        for black_domain in BLACKLIST_DOMAINS:
            if domain.endswith("." + black_domain):
                return True

        return False

    def _has_automotive_keywords(self, url: str) -> bool:
        """检查 URL 是否包含汽车关键词"""
        url_lower = url.lower()

        for keyword in AUTO_KEYWORDS:
            if keyword in url_lower:
                return True

        return False

    async def _update_or_create_candidate(
        self,
        session: AsyncSession,
        domain: str,
        links: List[Dict]
    ) -> str:
        """更新或创建候选源"""
        try:
            # 检查是否已存在
            result = await session.execute(
                select(SourceCandidate).where(SourceCandidate.domain == domain)
            )
            candidate = result.scalar_one_or_none()

            # 检查是否已是正式 source
            source_result = await session.execute(
                select(Source).where(Source.domain == domain)
            )
            existing_source = source_result.scalar_one_or_none()

            if existing_source:
                # 已是正式 source，跳过
                return "skipped"

            if candidate:
                # 更新现有候选
                candidate.mention_count += 1
                candidate.last_mentioned_at = datetime.now(timezone.utc)

                # 追加 discovered_from
                if candidate.discovered_from is None:
                    candidate.discovered_from = []

                for link in links:
                    if link["article_id"] not in [
                        item.get("article_id") for item in candidate.discovered_from
                    ]:
                        candidate.discovered_from.append({
                            "article_id": link["article_id"],
                            "article_title": link["article_title"],
                            "url": link["url"],
                        })

                # 如果 mention_count >= 5，标记为可分析
                if candidate.mention_count >= 5 and candidate.auto_analysis is None:
                    candidate.status = "pending_analysis"

                return "updated"

            else:
                # 创建新候选
                candidate = SourceCandidate(
                    domain=domain,
                    url=f"https://{domain}",
                    mention_count=len(links),
                    discovered_from=[
                        {
                            "article_id": link["article_id"],
                            "article_title": link["article_title"],
                            "url": link["url"],
                        }
                        for link in links
                    ],
                    status="pending_analysis" if len(links) >= 5 else "new",
                    first_mentioned_at=datetime.now(timezone.utc),
                    last_mentioned_at=datetime.now(timezone.utc),
                )

                session.add(candidate)
                return "created"

        except Exception as e:
            logger.error(f"Error updating candidate for {domain}: {e}")
            return "error"


# 全局单例
_link_collector: Optional[LinkCollector] = None


def get_link_collector(engine) -> LinkCollector:
    """获取全局外链收集器单例"""
    global _link_collector
    if _link_collector is None:
        _link_collector = LinkCollector(engine)
    return _link_collector
