"""
LLM 新源分析器

对 mention_count >= 5 的候选站点调用 LLM 分析其是否为汽车新闻源。

功能：
1. 抓取候选站点首页
2. 调用 GPT-4o-mini API 进行分析
3. 解析结果并更新 source_candidates 表
"""

import logging
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_session
from shared.models import SourceCandidate
from crawler.engine.fetcher import Fetcher

logger = logging.getLogger("crawler.discovery.analyzer")

# LLM 分析提示词
ANALYSIS_PROMPT = """分析以下网页内容，判断是否为汽车行业新闻站点。请用 JSON 格式回答：

{
  "is_automotive": true/false,
  "confidence": 0-1,
  "language": "ISO 639-1",
  "country": "ISO 3166-1 alpha-2",
  "update_frequency": "daily/weekly/monthly",
  "content_type": "news/review/forum/dealer/other",
  "uniqueness_score": 0-1,
  "reason": "简要说明"
}

网页内容：
{content}
"""


class LLMAnalyzer:
    """LLM 新源分析器"""

    def __init__(self, engine, fetcher: Fetcher):
        """
        初始化 LLM 分析器。

        参数:
            engine: SQLAlchemy async engine
            fetcher: Fetcher 实例
        """
        self.engine = engine
        self.fetcher = fetcher
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.daily_limit = 20
        self.analyzed_today = 0

    async def analyze_pending(self) -> Dict[str, int]:
        """
        分析所有待分析的候选站点。

        返回:
            统计信息字典
        """
        stats = {
            "candidates_analyzed": 0,
            "automotive_approved": 0,
            "non_automotive_rejected": 0,
            "errors": 0,
        }

        try:
            # 获取待分析的候选站点
            candidates = await self._get_pending_candidates()

            for candidate in candidates:
                # 检查每日限额
                if self.analyzed_today >= self.daily_limit:
                    logger.info(f"Daily limit reached: {self.analyzed_today}")
                    break

                # 分析候选站点
                result = await self._analyze_candidate(candidate)

                if result:
                    stats["candidates_analyzed"] += 1

                    if result.get("is_automotive"):
                        stats["automotive_approved"] += 1
                    else:
                        stats["non_automotive_rejected"] += 1
                else:
                    stats["errors"] += 1

            logger.info(
                f"Analysis completed: {stats['candidates_analyzed']} analyzed, "
                f"{stats['automotive_approved']} automotive, "
                f"{stats['non_automotive_rejected']} rejected"
            )

        except Exception as e:
            logger.error(f"Error in LLM analysis: {e}")

        return stats

    async def _get_pending_candidates(self) -> list:
        """获取待分析的候选站点"""
        try:
            async with get_session(self.engine) as session:
                result = await session.execute(
                    select(SourceCandidate)
                    .where(SourceCandidate.mention_count >= 5)
                    .where(SourceCandidate.auto_analysis.is_(None))
                    .where(SourceCandidate.status.in_(["new", "pending_analysis"]))
                    .order_by(SourceCandidate.mention_count.desc())
                    .limit(self.daily_limit)
                )

                return list(result.scalars().all())

        except Exception as e:
            logger.error(f"Error fetching pending candidates: {e}")
            return []

    async def _analyze_candidate(self, candidate: SourceCandidate) -> Optional[Dict]:
        """
        分析单个候选站点。

        参数:
            candidate: 候选站点对象

        返回:
            分析结果字典，失败返回 None
        """
        try:
            # 抓取候选站点首页
            url = candidate.url or f"https://{candidate.domain}"
            fetch_result = await self.fetcher.fetch(url, rendering="static")

            if not fetch_result.success or not fetch_result.html:
                logger.warning(f"Failed to fetch {url}")
                return None

            # 提取前 2000 字符文本
            content = self._extract_text(fetch_result.html)[:2000]

            if not content.strip():
                logger.warning(f"Empty content for {url}")
                return None

            # 调用 LLM API
            analysis_result = await self._call_llm(content)

            if not analysis_result:
                return None

            # 更新候选站点
            async with get_session(self.engine) as session:
                result = await session.execute(
                    select(SourceCandidate).where(SourceCandidate.id == candidate.id)
                )
                candidate = result.scalar_one_or_none()

                if candidate:
                    candidate.auto_analysis = analysis_result
                    candidate.analyzed_at = datetime.now(timezone.utc)

                    # 根据分析结果更新状态
                    if analysis_result.get("is_automotive"):
                        candidate.status = "pending"  # 等待人工审批
                    else:
                        candidate.status = "rejected"

                    await session.commit()

            self.analyzed_today += 1
            return analysis_result

        except Exception as e:
            logger.error(f"Error analyzing candidate {candidate.domain}: {e}")
            return None

    def _extract_text(self, html: str) -> str:
        """从 HTML 提取纯文本"""
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")

            # 移除脚本和样式
            for script in soup(["script", "style"]):
                script.decompose()

            # 获取文本
            text = soup.get_text(separator=" ", strip=True)

            # 清理多余空白
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            return " ".join(lines)

        except Exception as e:
            logger.error(f"Error extracting text: {e}")
            return ""

    async def _call_llm(self, content: str) -> Optional[Dict]:
        """
        调用 LLM API 进行分析。

        参数:
            content: 网页内容文本

        返回:
            分析结果字典
        """
        if not self.api_key:
            logger.warning("OpenAI API key not set, using mock analysis")
            return self._mock_analysis(content)

        try:
            import httpx

            prompt = ANALYSIS_PROMPT.format(content=content)

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
                            {"role": "system", "content": "You are a helpful assistant that analyzes websites."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 500,
                    },
                    timeout=30.0,
                )

                if response.status_code != 200:
                    logger.error(f"LLM API error: {response.status_code}")
                    return None

                result = response.json()
                content_text = result["choices"][0]["message"]["content"]

                # 解析 JSON
                # 尝试提取 JSON 部分
                json_start = content_text.find("{")
                json_end = content_text.rfind("}") + 1

                if json_start >= 0 and json_end > json_start:
                    json_str = content_text[json_start:json_end]
                    return json.loads(json_str)

                return None

        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            return None

    def _mock_analysis(self, content: str) -> Dict:
        """模拟分析（用于测试）"""
        content_lower = content.lower()

        # 简单的关键词匹配
        automotive_keywords = [
            "car", "auto", "vehicle", "motor", "ev", "electric",
            "toyota", "honda", "bmw", "mercedes", "tesla", "ford",
            "suv", "sedan", "truck", "engine", "driving", "road",
        ]

        keyword_count = sum(1 for kw in automotive_keywords if kw in content_lower)
        is_automotive = keyword_count >= 3

        return {
            "is_automotive": is_automotive,
            "confidence": min(0.5 + keyword_count * 0.1, 0.95),
            "language": "en",
            "country": "US",
            "update_frequency": "daily",
            "content_type": "news",
            "uniqueness_score": 0.5,
            "reason": f"Found {keyword_count} automotive keywords",
        }


# 全局单例
_llm_analyzer: Optional[LLMAnalyzer] = None


def get_llm_analyzer(engine, fetcher: Fetcher) -> LLMAnalyzer:
    """获取全局 LLM 分析器单例"""
    global _llm_analyzer
    if _llm_analyzer is None:
        _llm_analyzer = LLMAnalyzer(engine, fetcher)
    return _llm_analyzer
