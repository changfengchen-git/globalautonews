"""
自适应调频控制器

根据站点发布习惯自动调整抓取频率。

核心指标: discovery_rate = articles_new / articles_found

调频规则:
- discovery_rate > 0.5: 加速 (interval * 0.7, 最低 30 分钟)
- discovery_rate > 0.1: 保持
- discovery_rate > 0: 减速 (interval * 1.5, 最高 1440 分钟)
- discovery_rate == 0: 大幅减速 (interval * 2, 最高 1440 分钟)

发布时间模式学习:
- 统计每小时发布数量
- 统计每个工作日发布数量
- 在高峰时段缩短间隔
- 在低谷时段跳过抓取
"""

import logging
from datetime import datetime, timedelta, date
from typing import Optional, Dict, List, Tuple, Any
from collections import defaultdict

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("crawler.frequency")


class FrequencyController:
    """自适应调频控制器"""

    def __init__(self):
        """初始化调频控制器"""
        # 发布时间统计 (用于 Phase 5 的 T5.02)
        self._publish_hours: Dict[int, int] = defaultdict(int)  # hour -> count
        self._publish_weekdays: Dict[int, int] = defaultdict(int)  # weekday -> count

    def calculate_discovery_rate(self, articles_new: int, articles_found: int) -> float:
        """
        计算发现率。

        参数:
            articles_new: 新文章数量
            articles_found: 总发现文章数量

        返回:
            发现率 (0.0 - 1.0)
        """
        if articles_found == 0:
            return 0.0
        return articles_new / articles_found

    def calculate_new_interval(
        self,
        current_interval: int,
        discovery_rate: float,
        min_interval: int = 30,
        max_interval: int = 1440
    ) -> int:
        """
        根据发现率计算新的抓取间隔。

        参数:
            current_interval: 当前间隔（分钟）
            discovery_rate: 发现率
            min_interval: 最小间隔（分钟）
            max_interval: 最大间隔（分钟）

        返回:
            新的间隔（分钟）
        """
        if discovery_rate > 0.5:
            # 加速：发现率高，增加抓取频率
            new_interval = max(min_interval, int(current_interval * 0.7))
            logger.debug(f"Speed up: {current_interval} -> {new_interval} (rate={discovery_rate:.2f})")
        elif discovery_rate > 0.1:
            # 保持：发现率正常
            new_interval = current_interval
            logger.debug(f"Keep: {current_interval} (rate={discovery_rate:.2f})")
        elif discovery_rate > 0:
            # 减速：发现率低
            new_interval = min(max_interval, int(current_interval * 1.5))
            logger.debug(f"Slow down: {current_interval} -> {new_interval} (rate={discovery_rate:.2f})")
        else:
            # 大幅减速：零发现率
            new_interval = min(max_interval, int(current_interval * 2))
            logger.debug(f"Significant slow down: {current_interval} -> {new_interval} (rate={discovery_rate:.2f})")

        return new_interval

    def calculate_next_crawl_at(
        self,
        crawl_interval_minutes: int,
        base_time: Optional[datetime] = None
    ) -> datetime:
        """
        计算下次抓取时间。

        参数:
            crawl_interval_minutes: 抓取间隔（分钟）
            base_time: 基准时间（默认为当前时间）

        返回:
            下次抓取时间
        """
        if base_time is None:
            base_time = datetime.utcnow()
        return base_time + timedelta(minutes=crawl_interval_minutes)

    def calculate_avg_articles_per_crawl(
        self,
        current_avg: float,
        new_count: int,
        crawl_count: int
    ) -> float:
        """
        计算平均每次抓取的文章数（移动平均）。

        参数:
            current_avg: 当前平均值
            new_count: 本次新文章数
            crawl_count: 总抓取次数

        返回:
            新的平均值
        """
        if crawl_count <= 1:
            return float(new_count)
        # 指数移动平均 (EMA)
        alpha = 0.3
        return alpha * new_count + (1 - alpha) * current_avg

    def record_publish_time(self, publish_time: Optional[datetime]) -> None:
        """
        记录文章发布时间（用于分析发布模式）。

        参数:
            publish_time: 发布时间
        """
        if publish_time is None:
            return

        hour = publish_time.hour
        weekday = publish_time.weekday()  # 0=Monday, 6=Sunday

        self._publish_hours[hour] += 1
        self._publish_weekdays[weekday] += 1

    def get_publish_hours(self) -> Dict[int, int]:
        """获取按小时统计的发布时间分布"""
        return dict(self._publish_hours)

    def get_publish_weekdays(self) -> Dict[int, int]:
        """获取按星期统计的发布时间分布"""
        return dict(self._publish_weekdays)

    def get_peak_publish_hours(self, top_n: int = 3) -> List[int]:
        """
        获取发布高峰时段。

        参数:
            top_n: 返回前 N 个高峰时段

        返回:
            高峰小时列表
        """
        if not self._publish_hours:
            return []

        sorted_hours = sorted(
            self._publish_hours.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [hour for hour, _ in sorted_hours[:top_n]]

    def get_peak_publish_weekdays(self, top_n: int = 3) -> List[int]:
        """
        获取发布高峰日。

        参数:
            top_n: 返回前 N 个高峰日

        返回:
            高峰星期列表 (0=Monday, 6=Sunday)
        """
        if not self._publish_weekdays:
            return []

        sorted_weekdays = sorted(
            self._publish_weekdays.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [weekday for weekday, _ in sorted_weekdays[:top_n]]

    def update_source_frequency(
        self,
        current_interval: int,
        articles_new: int,
        articles_found: int,
        current_avg: float,
        crawl_count: int,
        publish_times: Optional[List[datetime]] = None
    ) -> Dict:
        """
        更新源的抓取频率。

        参数:
            current_interval: 当前抓取间隔（分钟）
            articles_new: 新文章数
            articles_found: 总发现文章数
            current_avg: 当前平均文章数
            crawl_count: 总抓取次数
            publish_times: 本次抓取的文章发布时间列表

        返回:
            包含更新后频率信息的字典
        """
        # 计算发现率
        discovery_rate = self.calculate_discovery_rate(articles_new, articles_found)

        # 计算新间隔
        new_interval = self.calculate_new_interval(current_interval, discovery_rate)

        # 计算新的平均文章数
        new_avg = self.calculate_avg_articles_per_crawl(
            current_avg, articles_new, crawl_count
        )

        # 记录发布时间
        if publish_times:
            for pt in publish_times:
                self.record_publish_time(pt)

        # 计算下次抓取时间
        next_crawl_at = self.calculate_next_crawl_at(new_interval)

        return {
            "crawl_interval_minutes": new_interval,
            "next_crawl_at": next_crawl_at,
            "discovery_rate": discovery_rate,
            "avg_articles_per_crawl": new_avg,
            "publish_hours": self.get_publish_hours(),
            "publish_weekdays": self.get_publish_weekdays(),
        }

    def reset(self) -> None:
        """重置统计数据"""
        self._publish_hours.clear()
        self._publish_weekdays.clear()

    async def learn_publish_patterns(
        self,
        source_id: int,
        session: AsyncSession,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        学习站点的发布时间模式。

        参数:
            source_id: 源 ID
            session: 数据库 session
            days: 统计最近多少天

        返回:
            发布模式统计
        """
        try:
            # 查询最近 N 天的文章
            cutoff_date = datetime.now() - timedelta(days=days)

            query = text("""
                SELECT published_at
                FROM articles
                WHERE source_id = :source_id
                AND published_at IS NOT NULL
                AND published_at >= :cutoff_date
                AND is_duplicate = FALSE
                ORDER BY published_at DESC
            """)

            result = await session.execute(
                query,
                {"source_id": source_id, "cutoff_date": cutoff_date}
            )
            rows = result.fetchall()

            if not rows:
                return {"hours": {}, "weekdays": {}, "peak_hours": [], "peak_weekdays": []}

            # 统计每小时发布数量
            hours_count = defaultdict(int)
            weekdays_count = defaultdict(int)

            for row in rows:
                published_at = row[0]
                if published_at:
                    hours_count[published_at.hour] += 1
                    weekdays_count[published_at.weekday()] += 1

            # 转换为普通字典
            hours_dict = {h: hours_count[h] for h in range(24)}
            weekdays_dict = {d: weekdays_count[d] for d in range(7)}

            # 找出高峰时段（前 3 个）
            sorted_hours = sorted(hours_count.items(), key=lambda x: x[1], reverse=True)
            peak_hours = [h for h, _ in sorted_hours[:3]]

            # 找出高峰日（前 3 个）
            sorted_weekdays = sorted(weekdays_count.items(), key=lambda x: x[1], reverse=True)
            peak_weekdays = [d for d, _ in sorted_weekdays[:3]]

            # 计算周末 vs 工作日比例
            weekday_total = sum(weekdays_count[d] for d in range(5))
            weekend_total = sum(weekdays_count[d] for d in range(5, 7))
            weekend_ratio = weekend_total / weekday_total if weekday_total > 0 else 0

            return {
                "hours": hours_dict,
                "weekdays": weekdays_dict,
                "peak_hours": peak_hours,
                "peak_weekdays": peak_weekdays,
                "weekend_ratio": weekend_ratio,
                "total_articles": len(rows),
            }

        except Exception as e:
            logger.error(f"Error learning publish patterns for source {source_id}: {e}")
            return {"hours": {}, "weekdays": {}, "peak_hours": [], "peak_weekdays": []}

    def should_crawl_now(
        self,
        publish_hours: Dict[int, int],
        publish_weekdays: Dict[int, int],
        current_hour: Optional[int] = None,
        current_weekday: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        根据发布时间模式判断是否应该现在抓取。

        参数:
            publish_hours: 每小时发布数量
            publish_weekdays: 每个工作日发布数量
            current_hour: 当前小时（默认当前时间）
            current_weekday: 当前星期（默认当前时间）

        返回:
            (should_crawl, reason)
        """
        if current_hour is None:
            current_hour = datetime.now().hour
        if current_weekday is None:
            current_weekday = datetime.now().weekday()

        # 检查是否有发布数据
        if not publish_hours or not publish_weekdays:
            return True, "no_pattern_data"

        # 检查当前小时是否有发布
        current_hour_count = publish_hours.get(current_hour, 0)
        total_articles = sum(publish_hours.values())

        if total_articles == 0:
            return True, "no_articles"

        # 如果当前小时发布量为 0，跳过
        if current_hour_count == 0:
            return False, "low_activity_hour"

        # 计算当前小时的发布比例
        hour_ratio = current_hour_count / total_articles

        # 如果当前小时发布比例 < 2%，跳过
        if hour_ratio < 0.02:
            return False, "very_low_activity_hour"

        # 检查周末
        if current_weekday >= 5:  # 周六或周日
            weekday_total = sum(publish_weekdays[d] for d in range(5))
            weekend_total = sum(publish_weekdays[d] for d in range(5, 7))

            if weekday_total > 0:
                weekend_ratio = weekend_total / (weekday_total * 2 / 5)  # 归一化
                if weekend_ratio < 0.3:
                    return False, "low_weekend_activity"

        return True, "normal_activity"

    def get_optimized_interval(
        self,
        base_interval: int,
        publish_hours: Dict[int, int],
        current_hour: Optional[int] = None
    ) -> int:
        """
        根据发布时间模式优化抓取间隔。

        参数:
            base_interval: 基础间隔（分钟）
            publish_hours: 每小时发布数量
            current_hour: 当前小时

        返回:
            优化后的间隔
        """
        if current_hour is None:
            current_hour = datetime.now().hour

        if not publish_hours:
            return base_interval

        # 找出高峰时段
        sorted_hours = sorted(publish_hours.items(), key=lambda x: x[1], reverse=True)
        peak_hours = [h for h, _ in sorted_hours[:3]]

        # 如果当前是高峰时段，缩短间隔
        if current_hour in peak_hours:
            return max(30, int(base_interval * 0.5))

        # 如果当前是低谷时段，延长间隔
        current_count = publish_hours.get(current_hour, 0)
        total = sum(publish_hours.values())

        if total > 0 and current_count / total < 0.02:
            return min(1440, int(base_interval * 2))

        return base_interval
