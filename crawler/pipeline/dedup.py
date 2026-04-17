"""
四级级联去重管线（L1 + L2 + L3，L4 在后续任务中添加）

核心类: DedupPipeline

公开方法:
    async def check_duplicate(
        url: str,
        title: str,
        language: str,
        session: AsyncSession
    ) -> DedupResult

DedupResult 数据类:
    is_duplicate: bool
    dedup_level: int | None    # 1, 2, 3, 4 或 None（非重复）
    duplicate_of: int | None   # 原始文章 ID
    details: str               # 去重详情描述

实现要求:

=== L1: URL 哈希去重 ===

1. URL 标准化：
   - 去除 URL 末尾的 / 
   - 去除 URL 中的 fragment (#xxx)
   - 去除常见追踪参数：utm_source, utm_medium, utm_campaign, ref, fbclid, gclid
   - 转为小写
   - 去除 www. 前缀

2. 计算标准化后 URL 的 SHA256 哈希

3. 查询 articles.url_hash 索引：
   ```sql
   SELECT id FROM articles WHERE url_hash = :hash LIMIT 1
   ```

4. 命中 → DedupResult(is_duplicate=True, dedup_level=1, duplicate_of=article_id)

=== L2: 标题 SimHash 指纹去重 ===

1. 标题预处理：
   - 去除标题中的特殊字符（保留字母、数字、CJK字符和空格）
   - 转小写（拉丁字母部分）
   - 去除多余空格

2. 计算标题的 SimHash（64位指纹）：
   - 使用 simhash 库
   - 对预处理后的标题文本分词：
     - 拉丁语系：按空格分词
     - CJK 语系：按 2-gram 字符分词

3. 查询同语种文章的 SimHash：
   ```sql
   SELECT id, title_simhash FROM articles
   WHERE language = :language
   AND title_simhash IS NOT NULL
   AND crawled_at > NOW() - INTERVAL '7 days'
   ```

4. 对每条结果计算汉明距离：
   ```python
   hamming = bin(simhash1 ^ simhash2).count('1')
   ```

5. 汉明距离 <= 3 → 判定为重复
   取汉明距离最小的那个作为 duplicate_of

=== L3: 实体+时间窗口去重 ===

1. 提取文章实体（品牌、车型）
2. 查询同语种、24h 时间窗口内的文章
3. 实体交集 >= 2 → 判定为同事件的不同报道
4. 标记为重复，关联到同一个 event_cluster

=== 辅助函数 ===

提供以下静态/工具函数供其他模块使用：

```python
@staticmethod
def normalize_url(url: str) -> str:
    '''标准化 URL'''
    ...

@staticmethod
def hash_url(url: str) -> str:
    '''计算 URL 的 SHA256 哈希'''
    ...

@staticmethod
def compute_simhash(text: str, language: str = "en") -> int:
    '''计算文本的 SimHash 指纹'''
    ...

@staticmethod
def hamming_distance(hash1: int, hash2: int) -> int:
    '''计算两个 SimHash 的汉明距离'''
    ...
```
"""
import hashlib
import re
import logging
from dataclasses import dataclass
from typing import Optional, List, Tuple
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from simhash import Simhash
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Article
from crawler.pipeline.entities import get_entity_extractor
from crawler.pipeline.embeddings import get_embedding_generator

logger = logging.getLogger("crawler.pipeline.dedup")

# URL 追踪参数黑名单
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "fbclid", "gclid", "mc_cid", "mc_eid",
    "source", "campaign", "medium",
}


@dataclass
class DedupResult:
    is_duplicate: bool = False
    dedup_level: Optional[int] = None
    duplicate_of: Optional[int] = None
    details: str = ""


class DedupPipeline:
    """四级级联去重管线"""

    def __init__(self, settings: Optional[dict] = None):
        """
        参数:
            settings: 配置字典，包含阈值等参数（来自 settings.yaml 的 dedup 部分）
        """
        self.simhash_threshold = (settings or {}).get("simhash_threshold", 3)

    async def check_duplicate(
        self,
        url: str,
        title: str,
        language: str,
        session: AsyncSession,
        content: str = "",
    ) -> DedupResult:
        """
        检查文章是否重复。按 L1 → L2 → L3 → L4 顺序检查，一旦命中立即返回。

        参数:
            url: 文章 URL
            title: 文章标题
            language: 文章语言代码
            session: 数据库 session
            content: 文章正文（用于 L3 实体提取和 L4 嵌入）

        返回:
            DedupResult
        """
        # L1: URL 哈希检查
        result = await self._check_l1(url, session)
        if result.is_duplicate:
            return result

        # L2: 标题 SimHash 检查
        result = await self._check_l2(title, language, session)
        if result.is_duplicate:
            return result

        # L3: 实体+时间窗口去重
        result = await self._check_l3(title, content, language, session)
        if result.is_duplicate:
            return result

        # L4: 向量相似度去重
        result = await self._check_l4(title, content, language, session)
        if result.is_duplicate:
            return result

        return DedupResult(is_duplicate=False, details="unique")

    async def _check_l1(self, url: str, session: AsyncSession) -> DedupResult:
        """L1: URL 哈希去重"""
        try:
            # 标准化 URL 并计算哈希
            url_hash = self.hash_url(url)
            
            # 查询数据库
            result = await session.execute(
                select(Article.id).where(Article.url_hash == url_hash).limit(1)
            )
            article_id = result.scalar_one_or_none()
            
            if article_id:
                logger.debug(f"L1 duplicate found: URL {url} -> article {article_id}")
                return DedupResult(
                    is_duplicate=True,
                    dedup_level=1,
                    duplicate_of=article_id,
                    details=f"URL hash match: {url_hash}"
                )
            
        except Exception as e:
            logger.error(f"Error in L1 dedup check: {e}")
        
        return DedupResult(is_duplicate=False, details="L1 unique")

    async def _check_l2(self, title: str, language: str, session: AsyncSession) -> DedupResult:
        """L2: 标题 SimHash 去重"""
        try:
            # 预处理标题并计算 SimHash
            processed_title = self._preprocess_title(title)
            if not processed_title:
                return DedupResult(is_duplicate=False, details="empty title")
            
            title_simhash = self.compute_simhash(processed_title, language)
            
            # 查询同语种文章的 SimHash
            # 注意：这里使用 raw SQL 因为 SQLAlchemy 不支持直接查询 BIGINT 的位运算
            query = text("""
                SELECT id, title_simhash FROM articles
                WHERE language = :language
                AND title_simhash IS NOT NULL
                AND crawled_at > NOW() - INTERVAL '7 days'
            """)
            
            result = await session.execute(query, {"language": language})
            rows = result.fetchall()
            
            min_distance = float('inf')
            duplicate_id = None
            
            for row in rows:
                article_id, existing_simhash = row
                if existing_simhash is None:
                    continue
                
                distance = self.hamming_distance(title_simhash, existing_simhash)
                if distance < min_distance:
                    min_distance = distance
                    duplicate_id = article_id
            
            if min_distance <= self.simhash_threshold and duplicate_id is not None:
                logger.debug(f"L2 duplicate found: title '{title[:50]}...' -> article {duplicate_id}, distance={min_distance}")
                return DedupResult(
                    is_duplicate=True,
                    dedup_level=2,
                    duplicate_of=duplicate_id,
                    details=f"SimHash distance: {min_distance}"
                )
            
        except Exception as e:
            logger.error(f"Error in L2 dedup check: {e}")
        
        return DedupResult(is_duplicate=False, details="L2 unique")

    def _preprocess_title(self, title: str) -> str:
        """预处理标题：去除特殊字符，转小写，去除多余空格"""
        if not title:
            return ""
        
        # 保留字母、数字、CJK字符和空格
        # CJK Unicode 范围：\u4e00-\u9fff（CJK 统一汉字）
        processed = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', title)
        
        # 转小写（只对 ASCII 字母）
        processed = ''.join(
            char.lower() if 'A' <= char <= 'Z' else char
            for char in processed
        )
        
        # 去除多余空格
        processed = ' '.join(processed.split())
        
        return processed

    # === 静态工具方法 ===

    @staticmethod
    def normalize_url(url: str) -> str:
        """URL 标准化"""
        try:
            # 解析 URL
            parsed = urlparse(url)
            
            # 转为小写（scheme 和 netloc）
            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower()
            
            # 去除 www. 前缀
            if netloc.startswith('www.'):
                netloc = netloc[4:]
            
            # 解析查询参数
            query_params = parse_qs(parsed.query)
            
            # 移除追踪参数
            filtered_params = {
                k: v for k, v in query_params.items()
                if k.lower() not in TRACKING_PARAMS
            }
            
            # 重新构建查询字符串
            new_query = urlencode(filtered_params, doseq=True)
            
            # 去除路径末尾的 /
            path = parsed.path
            if path.endswith('/') and len(path) > 1:
                path = path[:-1]
            
            # 去除 fragment
            fragment = ''
            
            # 重新构建 URL
            normalized = urlunparse((
                scheme, netloc, path,
                parsed.params, new_query, fragment
            ))
            
            return normalized
            
        except Exception as e:
            logger.warning(f"Failed to normalize URL {url}: {e}")
            return url

    @staticmethod
    def hash_url(url: str) -> str:
        """计算标准化 URL 的 SHA256"""
        normalized = DedupPipeline.normalize_url(url)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_simhash(text: str, language: str = "en") -> int:
        """
        计算文本的 SimHash。
        拉丁语系按空格分词，CJK 语系按 2-gram 分词。
        """
        if not text:
            return 0
        
        # 检测是否是 CJK 语言
        cjk_languages = {'zh', 'ja', 'ko', 'zh-HK', 'zh-TW', 'zh-CN'}
        is_cjk = language.lower() in cjk_languages
        
        if is_cjk:
            # CJK 语系：按 2-gram 字符分词
            tokens = []
            for i in range(len(text) - 1):
                tokens.append(text[i:i+2])
        else:
            # 拉丁语系：按空格分词
            tokens = text.split()
        
        # 计算 SimHash
        if not tokens:
            return 0
        
        simhash = Simhash(tokens)
        # 限制在 63 位内（有符号 64 位整数的正数范围）
        return simhash.value & 0x7FFFFFFFFFFFFFFF

    @staticmethod
    def hamming_distance(hash1: int, hash2: int) -> int:
        """计算两个哈希的汉明距离"""
        return bin(hash1 ^ hash2).count("1")

    async def _check_l3(
        self,
        title: str,
        content: str,
        language: str,
        session: AsyncSession
    ) -> DedupResult:
        """
        L3: 实体+时间窗口去重

        逻辑：
        1. 提取当前文章的实体（品牌、车型）
        2. 查询同语种、24h 时间窗口内的文章
        3. 实体交集 >= 2 → 判定为同事件的不同报道
        """
        try:
            # 提取当前文章的实体
            extractor = get_entity_extractor()
            entities = extractor.extract(text=content, title=title)

            current_brands = set(entities.get("brands", []))
            current_models = set(entities.get("models", []))
            current_entities = current_brands | current_models

            if len(current_entities) < 2:
                # 实体数量不足，跳过 L3 检查
                return DedupResult(is_duplicate=False, details="L3: insufficient entities")

            # 查询同语种、24h 时间窗口内的文章
            query = text("""
                SELECT id, title, content
                FROM articles
                WHERE language = :language
                AND is_duplicate = FALSE
                AND crawled_at > NOW() - INTERVAL '24 hours'
                ORDER BY crawled_at DESC
                LIMIT 100
            """)

            result = await session.execute(query, {"language": language})
            rows = result.fetchall()

            best_match_id = None
            best_intersection = 0

            for row in rows:
                article_id, existing_title, existing_content = row

                # 提取已有文章的实体
                existing_entities = extractor.extract(
                    text=existing_content or "",
                    title=existing_title or ""
                )
                existing_brands = set(existing_entities.get("brands", []))
                existing_models = set(existing_entities.get("models", []))
                existing_entity_set = existing_brands | existing_models

                # 计算实体交集
                intersection = current_entities & existing_entity_set

                if len(intersection) > best_intersection:
                    best_intersection = len(intersection)
                    best_match_id = article_id

            # 实体交集 >= 2 → 判定为重复
            if best_intersection >= 2 and best_match_id is not None:
                logger.debug(
                    f"L3 duplicate found: '{title[:50]}...' -> article {best_match_id}, "
                    f"intersection={best_intersection}"
                )
                return DedupResult(
                    is_duplicate=True,
                    dedup_level=3,
                    duplicate_of=best_match_id,
                    details=f"Entity intersection: {best_intersection}"
                )

        except Exception as e:
            logger.error(f"Error in L3 dedup check: {e}")

        return DedupResult(is_duplicate=False, details="L3 unique")

    async def _check_l4(
        self,
        title: str,
        content: str,
        language: str,
        session: AsyncSession
    ) -> DedupResult:
        """
        L4: 向量相似度去重（跨语种）

        逻辑：
        1. 计算文章的嵌入向量
        2. 使用 pgvector 查询相似文章
        3. 相似度 > 0.85 → 判定为跨语种重复
        """
        try:
            # 组合标题和正文前200字作为嵌入输入
            text_for_embedding = title
            if content:
                text_for_embedding += " " + content[:200]

            if not text_for_embedding.strip():
                return DedupResult(is_duplicate=False, details="L4: empty text")

            # 生成嵌入向量
            generator = get_embedding_generator()

            if not generator.is_available():
                logger.debug("Embedding generator not available, skipping L4")
                return DedupResult(is_duplicate=False, details="L4: generator not available")

            embedding = generator.generate(text_for_embedding)

            # 转换为字节格式存储（用于 pgvector）
            import numpy as np
            embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()

            # 使用 pgvector 查询相似文章
            query = text("""
                SELECT id, title, 1 - (embedding <=> :query_embedding) as similarity
                FROM articles
                WHERE embedding IS NOT NULL
                AND is_duplicate = FALSE
                AND crawled_at > NOW() - INTERVAL '3 days'
                ORDER BY embedding <=> :query_embedding
                LIMIT 5
            """)

            try:
                result = await session.execute(
                    query,
                    {"query_embedding": embedding_bytes}
                )
                rows = result.fetchall()
            except Exception as pgvector_error:
                # pgvector 可能不可用，回退到简单计算
                logger.debug(f"pgvector query failed: {pgvector_error}, using fallback")
                return await self._check_l4_fallback(embedding, session)

            # 检查相似度
            best_match_id = None
            best_similarity = 0.0

            for row in rows:
                article_id, existing_title, similarity = row
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_id = article_id

            # 相似度 > 0.85 → 判定为重复
            if best_similarity > 0.85 and best_match_id is not None:
                logger.debug(
                    f"L4 duplicate found: '{title[:50]}...' -> article {best_match_id}, "
                    f"similarity={best_similarity:.3f}"
                )
                return DedupResult(
                    is_duplicate=True,
                    dedup_level=4,
                    duplicate_of=best_match_id,
                    details=f"Embedding similarity: {best_similarity:.3f}"
                )

        except Exception as e:
            logger.error(f"Error in L4 dedup check: {e}")

        return DedupResult(is_duplicate=False, details="L4 unique")

    async def _check_l4_fallback(
        self,
        embedding,
        session: AsyncSession
    ) -> DedupResult:
        """
        L4 回退方法：当 pgvector 不可用时，使用简单计算
        """
        try:
            import numpy as np
            
            # 查询最近的文章
            query = text("""
                SELECT id, title, embedding
                FROM articles
                WHERE embedding IS NOT NULL
                AND is_duplicate = FALSE
                AND crawled_at > NOW() - INTERVAL '1 day'
                LIMIT 20
            """)

            result = await session.execute(query)
            rows = result.fetchall()

            generator = get_embedding_generator()
            best_match_id = None
            best_similarity = 0.0

            for row in rows:
                article_id, existing_title, existing_embedding_bytes = row

                if existing_embedding_bytes is None:
                    continue

                # 转换回 numpy 数组
                existing_embedding = np.frombuffer(existing_embedding_bytes, dtype=np.float32)

                # 计算余弦相似度
                similarity = generator.compute_similarity(embedding, existing_embedding)

                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match_id = article_id

            # 相似度 > 0.85 → 判定为重复
            if best_similarity > 0.85 and best_match_id is not None:
                logger.debug(
                    f"L4 (fallback) duplicate found -> article {best_match_id}, "
                    f"similarity={best_similarity:.3f}"
                )
                return DedupResult(
                    is_duplicate=True,
                    dedup_level=4,
                    duplicate_of=best_match_id,
                    details=f"Embedding similarity (fallback): {best_similarity:.3f}"
                )

        except Exception as e:
            logger.error(f"Error in L4 fallback check: {e}")

        return DedupResult(is_duplicate=False, details="L4 unique (fallback)")

    @staticmethod
    async def create_embedding_index(session: AsyncSession, threshold: int = 1000):
        """
        当 articles 表超过阈值时，创建 IVFFlat 索引

        参数:
            session: 数据库 session
            threshold: 触发创建索引的文章数量阈值
        """
        try:
            # 检查文章数量
            count_query = text("SELECT COUNT(*) FROM articles WHERE embedding IS NOT NULL")
            result = await session.execute(count_query)
            count = result.scalar()

            if count and count > threshold:
                # 检查索引是否已存在
                index_check = text("""
                    SELECT indexname FROM pg_indexes
                    WHERE tablename = 'articles'
                    AND indexname = 'idx_articles_embedding'
                """)
                result = await session.execute(index_check)
                index_exists = result.scalar()

                if not index_exists:
                    # 创建 IVFFlat 索引
                    create_index = text("""
                        CREATE INDEX idx_articles_embedding ON articles
                        USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
                    """)
                    await session.execute(create_index)
                    await session.commit()
                    logger.info(f"Created IVFFlat embedding index (articles count: {count})")

        except Exception as e:
            logger.error(f"Error creating embedding index: {e}")