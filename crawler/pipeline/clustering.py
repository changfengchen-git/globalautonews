"""
事件聚类模块

实现跨语种事件聚类，将同一事件的不同报道关联到同一个 event_cluster。

功能：
1. 新文章入库时的聚类逻辑
2. 更新 event_cluster 统计信息
3. 选择 representative 文章
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Set

from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models import Article, EventCluster

logger = logging.getLogger("crawler.pipeline.clustering")


class EventClusterManager:
    """事件聚类管理器"""

    def __init__(self):
        """初始化事件聚类管理器"""
        pass

    async def cluster_article(
        self,
        article: Article,
        session: AsyncSession,
        duplicate_of: Optional[int] = None
    ) -> Optional[EventCluster]:
        """
        将文章聚类到事件中。

        参数:
            article: 文章对象
            session: 数据库 session
            duplicate_of: 如果是重复文章，原始文章的 ID

        返回:
            关联的 EventCluster，如果创建新集群则返回新集群
        """
        try:
            if duplicate_of:
                # 如果是重复文章，尝试找到原始文章的 event_cluster
                cluster = await self._find_cluster_by_duplicate(duplicate_of, session)
                if cluster:
                    # 添加到现有集群
                    await self._add_to_cluster(article, cluster, session)
                    return cluster

            # 创建新的 event_cluster
            cluster = await self._create_new_cluster(article, session)
            return cluster

        except Exception as e:
            logger.error(f"Error clustering article {article.id}: {e}")
            return None

    async def _find_cluster_by_duplicate(
        self,
        duplicate_of: int,
        session: AsyncSession
    ) -> Optional[EventCluster]:
        """通过重复文章 ID 查找 event_cluster"""
        try:
            # 查找原始文章
            result = await session.execute(
                select(Article).where(Article.id == duplicate_of)
            )
            original_article = result.scalar_one_or_none()

            if not original_article:
                return None

            # 如果原始文章已有 cluster，返回它
            if original_article.event_cluster_id:
                result = await session.execute(
                    select(EventCluster).where(
                        EventCluster.id == original_article.event_cluster_id
                    )
                )
                return result.scalar_one_or_none()

            # 如果原始文章没有 cluster，为其创建一个
            cluster = await self._create_new_cluster(original_article, session)
            return cluster

        except Exception as e:
            logger.error(f"Error finding cluster for duplicate {duplicate_of}: {e}")
            return None

    async def _create_new_cluster(
        self,
        article: Article,
        session: AsyncSession
    ) -> EventCluster:
        """创建新的 event_cluster"""
        try:
            # 创建集群
            cluster = EventCluster(
                representative_id=article.id,
                article_count=1,
                languages=[article.language] if article.language else [],
                countries=[article.country] if article.country else [],
                language_count=1 if article.language else 0,
                country_count=1 if article.country else 0,
                importance_score=0.4,  # article_count=1, 其他为 0
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            session.add(cluster)
            await session.flush()  # 获取 cluster.id

            # 更新文章的 event_cluster_id
            article.event_cluster_id = cluster.id

            await session.flush()

            logger.debug(
                f"Created new event_cluster #{cluster.id} for article #{article.id}"
            )

            return cluster

        except Exception as e:
            logger.error(f"Error creating new cluster: {e}")
            raise

    async def _add_to_cluster(
        self,
        article: Article,
        cluster: EventCluster,
        session: AsyncSession
    ) -> None:
        """将文章添加到现有集群"""
        try:
            # 更新文章的 event_cluster_id
            article.event_cluster_id = cluster.id

            # 更新集群统计
            cluster.article_count += 1

            # 更新语言列表
            if article.language and article.language not in (cluster.languages or []):
                if cluster.languages is None:
                    cluster.languages = []
                cluster.languages.append(article.language)
                cluster.language_count = len(cluster.languages)

            # 更新国家列表
            if article.country and article.country not in (cluster.countries or []):
                if cluster.countries is None:
                    cluster.countries = []
                cluster.countries.append(article.country)
                cluster.country_count = len(cluster.countries)

            # 重新计算重要性分数
            cluster.importance_score = self._calculate_importance_score(cluster)

            # 更新 representative（如果新文章的语言覆盖更多）
            if cluster.language_count > 0:
                # 检查是否需要更新 representative
                current_rep = await self._get_representative(cluster.representative_id, session)
                if current_rep and article.language:
                    # 如果新文章的语言数量更多，更新 representative
                    # 这里简化处理：只在语言不同时考虑更新
                    pass

            cluster.updated_at = datetime.now(timezone.utc)

            await session.flush()

            logger.debug(
                f"Added article #{article.id} to event_cluster #{cluster.id}, "
                f"count={cluster.article_count}, languages={cluster.language_count}"
            )

        except Exception as e:
            logger.error(f"Error adding article to cluster: {e}")
            raise

    def _calculate_importance_score(self, cluster: EventCluster) -> float:
        """
        计算事件重要性分数。

        公式: importance_score = article_count * 0.4 + language_count * 0.3 + country_count * 0.3
        """
        article_count = cluster.article_count or 0
        language_count = cluster.language_count or 0
        country_count = cluster.country_count or 0

        score = (
            article_count * 0.4 +
            language_count * 0.3 +
            country_count * 0.3
        )

        return round(score, 2)

    async def _get_representative(
        self,
        article_id: int,
        session: AsyncSession
    ) -> Optional[Article]:
        """获取 representative 文章"""
        try:
            result = await session.execute(
                select(Article).where(Article.id == article_id)
            )
            return result.scalar_one_or_none()
        except Exception:
            return None

    async def update_cluster_stats(
        self,
        cluster_id: int,
        session: AsyncSession
    ) -> Optional[EventCluster]:
        """更新集群统计信息"""
        try:
            # 获取集群
            result = await session.execute(
                select(EventCluster).where(EventCluster.id == cluster_id)
            )
            cluster = result.scalar_one_or_none()

            if not cluster:
                return None

            # 查询集群中的所有文章
            result = await session.execute(
                select(Article).where(Article.event_cluster_id == cluster_id)
            )
            articles = result.scalars().all()

            # 统计语言和国家
            languages: Set[str] = set()
            countries: Set[str] = set()

            for article in articles:
                if article.language:
                    languages.add(article.language)
                if article.country:
                    countries.add(article.country)

            # 更新集群
            cluster.article_count = len(articles)
            cluster.languages = list(languages)
            cluster.countries = list(countries)
            cluster.language_count = len(languages)
            cluster.country_count = len(countries)
            cluster.importance_score = self._calculate_importance_score(cluster)
            cluster.updated_at = datetime.now(timezone.utc)

            await session.flush()

            return cluster

        except Exception as e:
            logger.error(f"Error updating cluster stats: {e}")
            return None

    async def get_cluster_articles(
        self,
        cluster_id: int,
        session: AsyncSession,
        limit: int = 50
    ) -> List[Article]:
        """获取集群中的所有文章"""
        try:
            result = await session.execute(
                select(Article)
                .where(Article.event_cluster_id == cluster_id)
                .order_by(Article.crawled_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error getting cluster articles: {e}")
            return []

    async def get_top_clusters(
        self,
        session: AsyncSession,
        limit: int = 20
    ) -> List[EventCluster]:
        """获取最重要的事件集群"""
        try:
            result = await session.execute(
                select(EventCluster)
                .order_by(EventCluster.importance_score.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
        except Exception as e:
            logger.error(f"Error getting top clusters: {e}")
            return []


# 全局单例
_cluster_manager: Optional[EventClusterManager] = None


def get_cluster_manager() -> EventClusterManager:
    """获取全局事件聚类管理器单例"""
    global _cluster_manager
    if _cluster_manager is None:
        _cluster_manager = EventClusterManager()
    return _cluster_manager
