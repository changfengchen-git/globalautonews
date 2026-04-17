"""
自动模板生成器

使用 LLM 分析页面结构，自动生成 YAML 适配器配置。
"""

import logging
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from shared.models import Source
from crawler.engine.fetcher import Fetcher
from crawler.extractors.adapter import AdapterExtractor, ExtractResult

logger = logging.getLogger("crawler.discovery.template_generator")

# LLM 生成适配器的提示词
ADAPTER_GENERATION_PROMPT = """分析以下网页的 HTML 结构，生成 YAML 格式的适配器配置。

请分析：
1. 列表页：文章列表的 CSS 选择器，文章链接的选择器
2. 文章页：标题、正文、日期、作者、图片的选择器

返回格式（YAML）：
```yaml
source_domain: {domain}
list_page:
  article_selector: "CSS选择器"
  link_selector: "CSS选择器"
  link_attribute: "href"
  max_links: 20
article_page:
  title_selector: "CSS选择器"
  content_selector: "CSS选择器"
  date_selector: "CSS选择器"
  date_format: "%Y-%m-%d"
  author_selector: "CSS选择器"
  image_selector: "CSS选择器"
  remove_selectors:
    - "div.ad"
    - "script"
    - "style"
```

列表页 HTML：
{list_html}

文章页 HTML：
{article_html}
"""


class TemplateGenerator:
    """自动模板生成器"""

    def __init__(self, engine, fetcher: Fetcher, adapters_dir: str = "crawler/adapters"):
        """
        初始化模板生成器。

        参数:
            engine: SQLAlchemy async engine
            fetcher: Fetcher 实例
            adapters_dir: 适配器配置文件目录
        """
        self.engine = engine
        self.fetcher = fetcher
        self.adapters_dir = Path(adapters_dir)
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    async def generate_for_source(self, source: Source) -> bool:
        """
        为指定源生成适配器。

        参数:
            source: Source 对象

        返回:
            是否成功生成
        """
        try:
            logger.info(f"Generating adapter for {source.domain}")

            # 1. 抓取列表页
            list_html = await self._fetch_list_page(source)
            if not list_html:
                logger.warning(f"Failed to fetch list page for {source.domain}")
                return False

            # 2. 抓取一篇文章页
            article_html, article_url = await self._fetch_article_page(source, list_html)
            if not article_html:
                logger.warning(f"Failed to fetch article page for {source.domain}")
                return False

            # 3. 调用 LLM 生成适配器
            adapter_config = await self._generate_adapter_yaml(
                source.domain, list_html, article_html
            )
            if not adapter_config:
                logger.warning(f"Failed to generate adapter config for {source.domain}")
                return False

            # 4. 测试适配器
            quality_passed = await self._test_adapter(source, adapter_config)
            if not quality_passed:
                logger.warning(f"Adapter test failed for {source.domain}")
                return False

            # 5. 保存适配器
            self._save_adapter(source.domain, adapter_config)

            # 6. 更新 source tier
            await self._upgrade_source_tier(source)

            logger.info(f"Adapter generated and saved for {source.domain}")
            return True

        except Exception as e:
            logger.error(f"Error generating template for {source.domain}: {e}")
            return False

    async def _fetch_list_page(self, source: Source) -> Optional[str]:
        """抓取列表页"""
        try:
            url = source.url or f"https://{source.domain}"
            result = await self.fetcher.fetch(url, rendering="static")

            if result.success and result.html:
                return result.html
            return None

        except Exception as e:
            logger.error(f"Error fetching list page: {e}")
            return None

    async def _fetch_article_page(self, source: Source, list_html: str) -> tuple:
        """从列表页提取一篇文章 URL 并抓取"""
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(list_html, "html.parser")

            # 查找文章链接
            links = soup.find_all("a", href=True)
            article_urls = []

            for link in links:
                href = link["href"]
                # 简单过滤：看起来像文章的 URL
                if any(ext in href.lower() for ext in [".html", ".htm", ".php", ".asp"]):
                    if href.startswith("/"):
                        href = f"https://{source.domain}{href}"
                    article_urls.append(href)

            if not article_urls:
                return None, None

            # 抓取第一篇文章
            for url in article_urls[:3]:  # 尝试最多 3 篇
                result = await self.fetcher.fetch(url, rendering="static")
                if result.success and result.html and len(result.html) > 1000:
                    return result.html, url

            return None, None

        except Exception as e:
            logger.error(f"Error fetching article page: {e}")
            return None, None

    async def _generate_adapter_yaml(
        self, domain: str, list_html: str, article_html: str
    ) -> Optional[Dict]:
        """调用 LLM 生成适配器配置"""
        if not self.api_key:
            logger.warning("No API key, using mock adapter generation")
            return self._mock_generate_adapter(domain)

        try:
            import httpx

            # 截取 HTML（减少 token）
            list_html_sample = list_html[:3000]
            article_html_sample = article_html[:5000]

            prompt = ADAPTER_GENERATION_PROMPT.format(
                domain=domain,
                list_html=list_html_sample,
                article_html=article_html_sample,
            )

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "You are a web scraping expert that generates YAML adapter configurations."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 1000,
                    },
                    timeout=60.0,
                )

                if response.status_code != 200:
                    logger.error(f"LLM API error: {response.status_code}")
                    return None

                result = response.json()
                content = result["choices"][0]["message"]["content"]

                # 提取 YAML 部分
                yaml_start = content.find("source_domain:")
                yaml_end = content.find("```", yaml_start)

                if yaml_start >= 0:
                    yaml_str = content[yaml_start:yaml_end] if yaml_end > yaml_start else content[yaml_start:]
                    return yaml.safe_load(yaml_str)

                return None

        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            return None

    def _mock_generate_adapter(self, domain: str) -> Dict:
        """生成 mock 适配器配置（用于测试）"""
        return {
            "source_domain": domain,
            "list_page": {
                "article_selector": "article",
                "link_selector": "a",
                "link_attribute": "href",
                "max_links": 20,
            },
            "article_page": {
                "title_selector": "h1",
                "content_selector": "article",
                "date_selector": "time",
                "date_format": "%Y-%m-%d",
                "author_selector": ".author",
                "image_selector": "article img:first-child",
                "remove_selectors": ["script", "style", ".ad"],
            },
        }

    async def _test_adapter(self, source: Source, adapter_config: Dict) -> bool:
        """测试适配器"""
        try:
            # 创建临时适配器
            adapter_extractor = AdapterExtractor()

            # 添加适配器配置
            from crawler.extractors.adapter import AdapterConfig
            adapter = AdapterConfig(
                source_domain=adapter_config["source_domain"],
                list_page=adapter_config.get("list_page", {}),
                article_page=adapter_config.get("article_page", {}),
            )
            adapter_extractor.adapters[source.domain] = adapter

            # 抓取列表页
            list_html = await self._fetch_list_page(source)
            if not list_html:
                return False

            # 提取文章 URL
            urls = adapter_extractor.extract_list(list_html, source.domain)
            if not urls:
                logger.warning(f"No URLs extracted for {source.domain}")
                return False

            # 测试提取 3 篇文章
            success_count = 0
            for url in urls[:3]:
                result = await self.fetcher.fetch(url, rendering="static")
                if result.success and result.html:
                    extract_result = adapter_extractor.extract_article(
                        result.html, url, source.domain
                    )
                    if extract_result.success and extract_result.content_length > 200:
                        success_count += 1

            # 至少 2 篇成功
            quality_passed = success_count >= 2
            logger.info(f"Adapter test: {success_count}/3 articles extracted successfully")
            return quality_passed

        except Exception as e:
            logger.error(f"Error testing adapter: {e}")
            return False

    def _save_adapter(self, domain: str, adapter_config: Dict) -> None:
        """保存适配器配置到文件"""
        try:
            # 确保目录存在
            self.adapters_dir.mkdir(parents=True, exist_ok=True)

            # 生成文件名
            filename = domain.replace(".", "_") + ".yaml"
            filepath = self.adapters_dir / filename

            # 写入 YAML
            with open(filepath, "w", encoding="utf-8") as f:
                yaml.dump(adapter_config, f, default_flow_style=False, allow_unicode=True)

            logger.info(f"Adapter saved to {filepath}")

        except Exception as e:
            logger.error(f"Error saving adapter: {e}")

    async def _upgrade_source_tier(self, source: Source) -> None:
        """升级 source tier 到 2"""
        try:
            async with get_session(self.engine) as session:
                result = await session.execute(
                    select(Source).where(Source.id == source.id)
                )
                source = result.scalar_one_or_none()

                if source:
                    source.tier = 2
                    await session.commit()
                    logger.info(f"Source #{source.id} upgraded to tier 2")

        except Exception as e:
            logger.error(f"Error upgrading source tier: {e}")


# 全局单例
_template_generator: Optional[TemplateGenerator] = None


def get_template_generator(engine, fetcher: Fetcher) -> TemplateGenerator:
    """获取全局模板生成器单例"""
    global _template_generator
    if _template_generator is None:
        _template_generator = TemplateGenerator(engine, fetcher)
    return _template_generator
