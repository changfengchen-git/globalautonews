"""
Tier 2 适配器引擎

基于 YAML 配置的声明式适配器，用于特定站点的精确提取。
"""

import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from datetime import datetime

import yaml
from bs4 import BeautifulSoup

logger = logging.getLogger("crawler.extractors.adapter")


@dataclass
class AdapterConfig:
    """适配器配置"""
    source_domain: str
    list_page: Dict[str, Any]
    article_page: Dict[str, Any]


@dataclass
class ExtractResult:
    """提取结果"""
    success: bool
    title: str = ""
    content: str = ""
    content_length: int = 0
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    image_url: Optional[str] = None
    image_urls: List[str] = None
    language: Optional[str] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.image_urls is None:
            self.image_urls = []


class AdapterExtractor:
    """Tier 2 适配器引擎"""

    def __init__(self, adapters_dir: str = "crawler/adapters"):
        """
        初始化适配器引擎。

        参数:
            adapters_dir: 适配器配置文件目录
        """
        self.adapters_dir = Path(adapters_dir)
        self.adapters: Dict[str, AdapterConfig] = {}
        self._load_adapters()

    def _load_adapters(self):
        """加载所有 YAML 适配器配置"""
        if not self.adapters_dir.exists():
            logger.warning(f"Adapters directory not found: {self.adapters_dir}")
            return

        for yaml_file in self.adapters_dir.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    config_data = yaml.safe_load(f)

                if not config_data or "source_domain" not in config_data:
                    logger.warning(f"Invalid adapter config: {yaml_file}")
                    continue

                adapter = AdapterConfig(
                    source_domain=config_data["source_domain"],
                    list_page=config_data.get("list_page", {}),
                    article_page=config_data.get("article_page", {}),
                )

                self.adapters[adapter.source_domain] = adapter
                logger.info(f"Loaded adapter for: {adapter.source_domain}")

            except Exception as e:
                logger.error(f"Error loading adapter {yaml_file}: {e}")

        logger.info(f"Loaded {len(self.adapters)} adapters")

    def has_adapter(self, domain: str) -> bool:
        """检查是否有该域名的适配器"""
        # 精确匹配
        if domain in self.adapters:
            return True

        # 检查子域名（如 www.example.com 匹配 example.com）
        domain_parts = domain.split(".")
        if len(domain_parts) > 2:
            parent_domain = ".".join(domain_parts[-2:])
            return parent_domain in self.adapters

        return False

    def get_adapter(self, domain: str) -> Optional[AdapterConfig]:
        """获取适配器配置"""
        if domain in self.adapters:
            return self.adapters[domain]

        # 检查子域名
        domain_parts = domain.split(".")
        if len(domain_parts) > 2:
            parent_domain = ".".join(domain_parts[-2:])
            if parent_domain in self.adapters:
                return self.adapters[parent_domain]

        return None

    def extract_list(self, html: str, domain: str) -> List[str]:
        """
        从列表页提取文章 URL 列表。

        参数:
            html: 列表页 HTML
            domain: 域名

        返回:
            文章 URL 列表
        """
        adapter = self.get_adapter(domain)
        if not adapter:
            logger.warning(f"No adapter for domain: {domain}")
            return []

        list_config = adapter.list_page
        if not list_config:
            return []

        try:
            soup = BeautifulSoup(html, "html.parser")

            # 获取文章选择器
            article_selector = list_config.get("article_selector")
            if not article_selector:
                return []

            # 查找所有文章元素
            articles = soup.select(article_selector)
            if not articles:
                return []

            # 获取链接选择器和属性
            link_selector = list_config.get("link_selector", "a")
            link_attribute = list_config.get("link_attribute", "href")

            urls = []
            for article in articles:
                # 查找链接
                link = article.select_one(link_selector)
                if link:
                    url = link.get(link_attribute)
                    if url:
                        # 转换为绝对 URL
                        if url.startswith("/"):
                            url = f"https://{domain}{url}"
                        elif not url.startswith("http"):
                            continue
                        urls.append(url)

            # 限制数量
            max_links = list_config.get("max_links", 30)
            return urls[:max_links]

        except Exception as e:
            logger.error(f"Error extracting list for {domain}: {e}")
            return []

    def extract_article(self, html: str, url: str, domain: str) -> ExtractResult:
        """
        使用适配器提取文章内容。

        参数:
            html: 文章页 HTML
            url: 文章 URL
            domain: 域名

        返回:
            ExtractResult
        """
        adapter = self.get_adapter(domain)
        if not adapter:
            return ExtractResult(success=False, error=f"No adapter for {domain}")

        article_config = adapter.article_page
        if not article_config:
            return ExtractResult(success=False, error="No article_page config")

        try:
            soup = BeautifulSoup(html, "html.parser")

            # 移除不需要的元素
            remove_selectors = article_config.get("remove_selectors", [])
            for selector in remove_selectors:
                for element in soup.select(selector):
                    element.decompose()

            # 提取标题
            title = self._extract_text(soup, article_config.get("title_selector"))

            # 提取内容
            content = self._extract_text(soup, article_config.get("content_selector"))

            # 提取作者
            author = self._extract_text(soup, article_config.get("author_selector"))

            # 提取日期
            published_at = self._extract_date(soup, article_config)

            # 提取图片
            image_url = self._extract_image(soup, article_config.get("image_selector"))
            image_urls = self._extract_images(soup, article_config.get("content_selector"))

            if not title and not content:
                return ExtractResult(success=False, error="No content extracted")

            return ExtractResult(
                success=True,
                title=title,
                content=content,
                content_length=len(content),
                author=author,
                published_at=published_at,
                image_url=image_url,
                image_urls=image_urls,
            )

        except Exception as e:
            logger.error(f"Error extracting article from {url}: {e}")
            return ExtractResult(success=False, error=str(e))

    def _extract_text(self, soup: BeautifulSoup, selector: Optional[str]) -> str:
        """提取文本"""
        if not selector:
            return ""

        element = soup.select_one(selector)
        if element:
            return element.get_text(strip=True)
        return ""

    def _extract_date(self, soup: BeautifulSoup, config: Dict) -> Optional[datetime]:
        """提取日期"""
        date_selector = config.get("date_selector")
        if not date_selector:
            return None

        element = soup.select_one(date_selector)
        if not element:
            return None

        try:
            # 从属性获取日期
            date_attribute = config.get("date_attribute")
            if date_attribute:
                date_str = element.get(date_attribute)
            else:
                date_str = element.get_text(strip=True)

            if not date_str:
                return None

            # 解析日期
            date_format = config.get("date_format", "%Y-%m-%d")
            return datetime.strptime(date_str[:19], date_format[:19])

        except Exception as e:
            logger.debug(f"Error parsing date: {e}")
            return None

    def _extract_image(self, soup: BeautifulSoup, selector: Optional[str]) -> Optional[str]:
        """提取单张图片"""
        if not selector:
            return None

        element = soup.select_one(selector)
        if element:
            return element.get("src")
        return None

    def _extract_images(self, soup: BeautifulSoup, selector: Optional[str]) -> List[str]:
        """提取多张图片"""
        if not selector:
            return []

        container = soup.select_one(selector)
        if not container:
            return []

        images = container.select("img")
        return [img.get("src") for img in images if img.get("src")]

    def get_loaded_adapters(self) -> List[str]:
        """获取已加载的适配器列表"""
        return list(self.adapters.keys())


# 全局单例
_adapter_extractor: Optional[AdapterExtractor] = None


def get_adapter_extractor() -> AdapterExtractor:
    """获取全局适配器引擎单例"""
    global _adapter_extractor
    if _adapter_extractor is None:
        _adapter_extractor = AdapterExtractor()
    return _adapter_extractor
