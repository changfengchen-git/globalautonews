"""
Tier 1: 通用提取器

核心类: GenericExtractor

公开方法:
    def extract(html: str, url: str) -> ExtractResult

ExtractResult 数据类:
    title: str | None
    content: str | None        # 纯文本正文（已去除 HTML 标签）
    author: str | None
    published_at: datetime | None
    excerpt: str | None        # 正文前 300 字符
    image_url: str | None      # 题图 URL
    image_urls: list[str]      # 文中所有图片 URL
    external_links: list[str]  # 文中所有外部链接
    language: str | None       # 检测到的语言
    content_length: int        # 正文字符数
    quality_score: float       # 提取质量评分 (0-1)
    success: bool              # 是否提取成功

实现要求:

1. 使用 trafilatura 的 extract() 函数提取正文：
   ```python
   import trafilatura
   result = trafilatura.extract(
       html,
       url=url,
       include_comments=False,
       include_tables=True,
       include_images=True,
       include_links=True,
       output_format="txt",  # 纯文本
       with_metadata=True,
   )
   ```

2. 元数据提取（从 trafilatura 的 bare_extraction 获取更多元数据）：
   ```python
   metadata = trafilatura.bare_extraction(html, url=url, with_metadata=True)
   # metadata 包含: title, author, date, description, image, etc.
   ```

3. 图片 URL 提取：
   - 题图：优先使用 trafilatura 提取的 image，其次使用 og:image meta 标签
   - 文中图片：用 BeautifulSoup 或正则从原始 HTML 中提取所有 <img> 的 src
   - 将相对 URL 转为绝对 URL

4. 外部链接提取：
   - 从原始 HTML 中提取所有 <a href="...">
   - 只保留外部链接（域名与当前页面不同的）
   - 排除常见非新闻链接：javascript:, mailto:, #锚点, 登录页等
   - 存入 external_links 列表（供"自我生长"使用）

5. 语言检测：
   - 使用 langdetect 库检测正文语言
   - 返回 ISO 639-1 代码（如 en, zh, ja, de 等）

6. 质量评分 (quality_score)：
   用于判断是否需要降级到 Tier 2。评分规则：
   - 标题非空：+0.25
   - 正文长度 >= 200 字符：+0.25
   - 正文长度 >= 500 字符：+0.15
   - 有发布时间：+0.15
   - HTML 标签残留 < 3%：+0.1（用正则 <[^>]+> 检测）
   - 有图片：+0.1

   quality_score < 0.5 → success = False（建议降级到 Tier 2）

7. excerpt 生成：
   - 取正文前 300 个字符
   - 在最后一个完整句子（。！？.!?）处截断
   - 如果 300 字符内没有句号，直接截断加 "..."

8. 发布时间解析：
   - 优先使用 trafilatura 提取的 date
   - 解析为 datetime 对象（带时区，默认 UTC）
   - 解析失败返回 None
"""
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from urllib.parse import urljoin, urlparse

import trafilatura
from bs4 import BeautifulSoup

logger = logging.getLogger("crawler.extractor.generic")


# 外部链接过滤黑名单域名
LINK_BLACKLIST_DOMAINS = {
    # 社交媒体
    "facebook.com", "twitter.com", "x.com", "instagram.com",
    "linkedin.com", "pinterest.com", "tiktok.com", "reddit.com",
    "youtube.com", "youtu.be", "t.me", "telegram.org",
    # 搜索引擎
    "google.com", "bing.com", "yahoo.com", "baidu.com",
    # 广告/追踪
    "doubleclick.net", "googlesyndication.com", "googleadservices.com",
    "amazon.com", "amzn.to",
    # CDN/工具
    "cloudflare.com", "jsdelivr.net", "cdnjs.com",
    "gravatar.com", "wp.com",
    # 应用商店
    "apps.apple.com", "play.google.com",
}


@dataclass
class ExtractResult:
    title: Optional[str] = None
    content: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    excerpt: Optional[str] = None
    image_url: Optional[str] = None
    image_urls: List[str] = field(default_factory=list)
    external_links: List[str] = field(default_factory=list)
    language: Optional[str] = None
    content_length: int = 0
    quality_score: float = 0.0
    success: bool = False


class GenericExtractor:
    """Tier 1 通用新闻提取器"""

    def extract(self, html: str, url: str) -> ExtractResult:
        """
        从 HTML 中提取新闻文章内容。

        参数:
            html: 页面 HTML 源码
            url: 页面 URL（用于解析相对链接）

        返回:
            ExtractResult 对象
        """
        result = ExtractResult()
        
        try:
            # 1. 使用 trafilatura 提取正文和元数据
            extracted_text = trafilatura.extract(
                html,
                url=url,
                include_comments=False,
                include_tables=True,
                include_images=True,
                include_links=True,
                output_format="txt",
                with_metadata=True,
            )
            
            # 使用 bare_extraction 获取更多元数据
            metadata = trafilatura.bare_extraction(
                html,
                url=url,
                with_metadata=True,
                include_comments=False,
                include_tables=True,
                include_images=True,
                include_links=True,
            )
            
            if not metadata and not extracted_text:
                logger.warning(f"No content extracted from {url}")
                return result
            
            # 2. 提取标题
            result.title = metadata.title if metadata else None
            
            # 3. 提取正文
            result.content = extracted_text or (metadata.text if metadata else None)
            if result.content:
                result.content_length = len(result.content)
            
            # 检查是否是新闻文章（排除隐私协议、网站介绍等）
            if not self._is_news_article(url, result.title, result.content):
                logger.debug(f"Skipping non-news page: {url}")
                return result
            
            # 4. 提取作者
            result.author = metadata.author if metadata else None
            
            # 5. 提取发布时间
            date_str = metadata.date if metadata else None
            result.published_at = self._parse_date(date_str)
            
            # 6. 提取图片
            metadata_image = metadata.image if metadata else None
            result.image_url, result.image_urls = self._extract_images(html, url, metadata_image)
            
            # 7. 提取外部链接
            result.external_links = self._extract_external_links(html, url)
            
            # 8. 检测语言
            if result.content:
                result.language = self._detect_language(result.content)
            
            # 9. 生成摘要
            if result.content:
                result.excerpt = self._generate_excerpt(result.content)
            
            # 10. 计算质量评分
            result.quality_score = self._calculate_quality(result, html)
            
            # 11. 判断是否成功
            result.success = result.quality_score >= 0.5
            
            logger.debug(f"Extracted from {url}: title={result.title[:50] if result.title else 'None'}, "
                        f"content_length={result.content_length}, quality={result.quality_score:.2f}")
            
        except Exception as e:
            logger.error(f"Error extracting from {url}: {e}")
        
        return result

    def _extract_images(self, html: str, base_url: str, metadata_image: Optional[str] = None) -> Tuple[Optional[str], List[str]]:
        """提取题图和文中图片 URL 列表"""
        image_url = None
        image_urls = []
        
        try:
            # 使用 BeautifulSoup 提取所有图片
            soup = BeautifulSoup(html, 'html.parser')
            img_tags = soup.find_all('img')
            
            for img in img_tags:
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src:
                    # 转换为绝对 URL
                    absolute_url = urljoin(base_url, src)
                    image_urls.append(absolute_url)
            
            # 去重
            image_urls = list(dict.fromkeys(image_urls))
            
            # 优先使用 metadata_image
            if metadata_image:
                image_url = urljoin(base_url, metadata_image)
            else:
                # 尝试从 og:image 获取题图
                og_image = None
                meta_tags = soup.find_all('meta', property='og:image')
                if meta_tags:
                    og_image = meta_tags[0].get('content')
                
                if og_image:
                    image_url = urljoin(base_url, og_image)
                elif image_urls:
                    image_url = image_urls[0]
                
        except Exception as e:
            logger.debug(f"Error extracting images: {e}")
        
        return image_url, image_urls

    def _extract_external_links(self, html: str, base_url: str) -> List[str]:
        """提取外部链接列表（排除本站、社交媒体、广告等）"""
        external_links = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            a_tags = soup.find_all('a', href=True)
            
            base_domain = urlparse(base_url).netloc.lower()
            if base_domain.startswith('www.'):
                base_domain = base_domain[4:]
            
            for a in a_tags:
                href = a['href']
                
                # 跳过非 HTTP 链接
                if not href.startswith(('http://', 'https://')):
                    continue
                
                # 解析链接域名
                try:
                    link_domain = urlparse(href).netloc.lower()
                    if link_domain.startswith('www.'):
                        link_domain = link_domain[4:]
                except Exception:
                    continue
                
                # 跳过本站链接
                if link_domain == base_domain:
                    continue
                
                # 跳过黑名单域名
                if self._is_blacklisted_domain(link_domain):
                    continue
                
                # 跳过常见非新闻链接
                if self._is_non_news_link(href):
                    continue
                
                external_links.append(href)
            
            # 去重
            external_links = list(dict.fromkeys(external_links))
            
        except Exception as e:
            logger.debug(f"Error extracting external links: {e}")
        
        return external_links

    def _is_blacklisted_domain(self, domain: str) -> bool:
        """检查域名是否在黑名单中"""
        for black_domain in LINK_BLACKLIST_DOMAINS:
            if domain == black_domain or domain.endswith('.' + black_domain):
                return True
        return False

    def _is_non_news_link(self, url: str) -> bool:
        """检查是否是非新闻链接"""
        url_lower = url.lower()
        
        # 常见非新闻链接模式
        non_news_patterns = [
            'javascript:', 'mailto:', 'tel:', '#',
            '/login', '/signup', '/register', '/account',
            '/cart', '/checkout', '/payment',
            '/privacy', '/terms', '/about', '/contact',
            '/search?', '/tag/', '/category/',
        ]
        
        for pattern in non_news_patterns:
            if pattern in url_lower:
                return True
        
        return False

    def _detect_language(self, text: str) -> Optional[str]:
        """检测文本语言"""
        try:
            from langdetect import detect, LangDetectException
            
            # 只检测前 1000 个字符以提高速度
            sample = text[:1000] if len(text) > 1000 else text
            
            if not sample.strip():
                return None
            
            lang = detect(sample)
            return lang
            
        except (ImportError, LangDetectException) as e:
            logger.debug(f"Language detection failed: {e}")
            return None

    def _calculate_quality(self, result: ExtractResult, html: str) -> float:
        """计算提取质量评分"""
        score = 0.0
        
        # 标题非空：+0.25
        if result.title and result.title.strip():
            score += 0.25
        
        # 正文长度 >= 200 字符：+0.25
        if result.content_length >= 200:
            score += 0.25
        
        # 正文长度 >= 500 字符：+0.15
        if result.content_length >= 500:
            score += 0.15
        
        # 有发布时间：+0.15
        if result.published_at:
            score += 0.15
        
        # HTML 标签残留 < 3%：+0.1
        if result.content and html:
            # 计算 HTML 标签比例
            tag_count = len(re.findall(r'<[^>]+>', html))
            html_length = len(html)
            if html_length > 0:
                tag_ratio = tag_count / html_length
                if tag_ratio < 0.03:
                    score += 0.1
        
        # 有图片：+0.1
        if result.image_url or result.image_urls:
            score += 0.1
        
        return min(score, 1.0)  # 确保不超过 1.0

    def _generate_excerpt(self, content: str, max_length: int = 300) -> str:
        """生成摘要"""
        if not content:
            return ""
        
        # 取前 max_length 个字符
        if len(content) <= max_length:
            return content
        
        excerpt = content[:max_length]
        
        # 查找最后一个完整句子的结束位置
        sentence_endings = ['。', '！', '？', '.', '!', '?']
        last_period_pos = -1
        
        for ending in sentence_endings:
            pos = excerpt.rfind(ending)
            if pos > last_period_pos:
                last_period_pos = pos
        
        if last_period_pos > max_length * 0.5:  # 至少在 50% 位置后
            return excerpt[:last_period_pos + 1]
        else:
            # 没有找到合适的句号，直接截断
            return excerpt.rstrip() + "..."

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """解析发布日期"""
        if not date_str:
            return None
        
        try:
            # 尝试多种日期格式
            from dateutil import parser as date_parser
            
            # 使用 dateutil 解析
            dt = date_parser.parse(date_str)
            
            # 如果没有时区信息，添加 UTC 时区
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            
            return dt
            
        except Exception as e:
            logger.debug(f"Failed to parse date '{date_str}': {e}")
            return None

    def _is_news_article(self, url: str, title: Optional[str], content: Optional[str]) -> bool:
        """
        判断页面是否是新闻文章，排除非新闻页面
        
        返回: True 表示是新闻文章，False 表示应该跳过
        """
        # URL 路径排除模式（非新闻页面）
        url_exclude_patterns = [
            # 隐私和条款
            '/privacy', '/privacy-policy', '/privacypolicy',
            '/terms', '/terms-of-service', '/terms-and-conditions', '/tos',
            '/legal', '/disclaimer',
            # 关于页面
            '/about', '/about-us', '/about-us', '/about.html',
            '/contact', '/contact-us', '/contact.html',
            '/team', '/staff', '/editorial',
            # 用户相关
            '/login', '/signin', '/sign-in', '/register', '/signup', '/sign-up',
            '/account', '/profile', '/settings', '/dashboard',
            '/subscribe', '/subscription', '/membership',
            # 静态页面
            '/faq', '/help', '/support', '/sitemap', '/sitemap.xml',
            '/advertise', '/advertising', '/partners',
            '/careers', '/jobs',
            # 订阅和通讯
            '/newsletter', '/newsletters', '/podcast', '/podcasts',
            '/video', '/videos', '/live', '/live-tv',
            # 商城
            '/shop', '/store', '/cart', '/checkout',
        ]
        
        url_lower = url.lower()
        path = urlparse(url).path.lower()
        
        # 检查 URL 路径是否匹配排除模式
        for pattern in url_exclude_patterns:
            if path.endswith(pattern) or path.endswith(pattern + '/'):
                logger.debug(f"Skipping non-news URL (matches {pattern}): {url}")
                return False
        
        # 标题排除关键词
        title_exclude_keywords = [
            'privacy policy', 'privacy notice', 'terms of service', 'terms and conditions',
            'about us', 'about the company', 'contact us', 'contact information',
            'cookie policy', 'cookie notice', 'disclaimer',
            'subscribe', 'subscription', 'newsletter signup',
            'sign in', 'sign up', 'log in', 'register',
            'advertisement', 'advertise with us', 'sponsored',
            'editorial policy', 'corrections', 'fact-checking',
        ]
        
        if title:
            title_lower = title.lower()
            for keyword in title_exclude_keywords:
                if keyword in title_lower:
                    logger.debug(f"Skipping non-news article (title contains '{keyword}'): {url}")
                    return False
        
        # 内容排除模式（内容太短或包含特定关键词）
        if content:
            content_lower = content.lower()
            content_length = len(content)
            
            # 内容太短，可能是导航页或占位页
            if content_length < 100:
                logger.debug(f"Skipping page with too little content ({content_length} chars): {url}")
                return False
            
            # 检查是否是纯导航/菜单内容
            nav_keywords = ['home', 'news', 'sports', 'entertainment', 'business', 'technology']
            nav_keyword_count = sum(1 for kw in nav_keywords if kw in content_lower)
            if nav_keyword_count >= 5 and content_length < 500:
                logger.debug(f"Skipping navigation page: {url}")
                return False
        
        return True