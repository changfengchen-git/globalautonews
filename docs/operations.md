# GlobalAutoNews 运维文档

## 目录

1. [部署步骤](#部署步骤)
2. [常用运维命令](#常用运维命令)
3. [故障排查指南](#故障排查指南)
4. [备份恢复流程](#备份恢复流程)
5. [如何添加新站点](#如何添加新站点)
6. [如何编写 Tier 2 适配器](#如何编写-tier-2-适配器)
7. [如何编写 Tier 3 定制爬虫](#如何编写-tier-3-定制爬虫)
8. [定时任务清单](#定时任务清单)

---

## 部署步骤

### 1. 环境准备

```bash
# 克隆仓库
git clone <repository-url>
cd globalautonews

# 复制环境变量配置
cp .env.example .env
# 编辑 .env 文件，配置数据库密码等

# 安装 Docker 和 Docker Compose
# 参考: https://docs.docker.com/compose/install/
```

### 2. 启动服务

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

### 3. 初始化数据库

```bash
# 数据库会在首次启动时自动初始化
# 验证数据库连接
docker-compose exec db psql -U gan -d globalautonews -c "\dt"
```

### 4. 导入初始站点

```bash
# 导入 199 个汽车新闻站点
docker-compose exec crawler python scripts/seed_sources.py
```

### 5. 验证部署

```bash
# 访问 API 文档
# http://localhost:8000/docs

# 访问前端
# http://localhost:80

# 检查健康状态
curl http://localhost:8000/api/health
```

---

## 常用运维命令

### 服务管理

```bash
# 启动所有服务
docker-compose up -d

# 停止所有服务
docker-compose down

# 重启特定服务
docker-compose restart crawler

# 查看服务状态
docker-compose ps

# 查看资源使用
docker stats
```

### 日志查看

```bash
# 查看所有日志
docker-compose logs -f

# 查看特定服务日志
docker-compose logs -f crawler
docker-compose logs -f api

# 查看最近 100 行日志
docker-compose logs --tail=100 crawler
```

### 数据库操作

```bash
# 连接数据库
docker-compose exec db psql -U gan -d globalautonews

# 查看表结构
\dt

# 查看统计信息
SELECT COUNT(*) FROM articles;
SELECT COUNT(*) FROM sources;
SELECT COUNT(*) FROM event_clusters;

# 手动清理旧日志
DELETE FROM crawl_logs WHERE started_at < NOW() - INTERVAL '30 days';
```

### 数据导出

```bash
# 导出数据库
docker-compose exec db pg_dump -U gan globalautonews > backup.sql

# 导入数据库
docker-compose exec -T db psql -U gan globalautonews < backup.sql
```

---

## 故障排查指南

### 问题 1: Crawler 无法抓取

**症状**: crawl_logs 中显示大量错误

**排查步骤**:
1. 检查网络连接
   ```bash
   docker-compose exec crawler curl -I https://www.google.com
   ```

2. 检查 Fetcher 配置
   ```bash
   docker-compose exec crawler cat config/settings.yaml
   ```

3. 查看具体错误日志
   ```bash
   docker-compose logs crawler | grep ERROR
   ```

### 问题 2: 数据库连接失败

**症状**: API 返回 500 错误

**排查步骤**:
1. 检查数据库状态
   ```bash
   docker-compose exec db pg_isready -U gan
   ```

2. 检查连接数
   ```bash
   docker-compose exec db psql -U gan -d globalautonews -c "SELECT count(*) FROM pg_stat_activity;"
   ```

### 问题 3: 前端页面空白

**症状**: 访问 http://localhost 显示空白或错误

**排查步骤**:
1. 检查 Nginx 状态
   ```bash
   docker-compose exec web nginx -t
   ```

2. 检查前端构建
   ```bash
   docker-compose exec web ls -la /usr/share/nginx/html
   ```

3. 检查 API 代理
   ```bash
   docker-compose exec web curl http://localhost/api/health
   ```

### 问题 4: 内存不足

**症状**: 容器频繁重启

**排查步骤**:
1. 查看资源使用
   ```bash
   docker stats
   ```

2. 调整 docker-compose.yml 中的内存限制
3. 考虑减少并发数（MAX_CONCURRENCY）

---

## 备份恢复流程

### 自动备份（推荐）

配置 cron 任务每日备份：

```bash
# 编辑 crontab
crontab -e

# 添加以下行（每日凌晨 2 点备份）
0 2 * * * cd /path/to/globalautonews && docker-compose exec -T db pg_dump -U gan globalautonews > backup_$(date +%Y%m%d).sql
```

### 手动备份

```bash
# 完整备份
docker-compose exec db pg_dump -U gan -Fc globalautonews > backup.dump

# 仅备份数据（不含 schema）
docker-compose exec db pg_dump -U gan --data-only globalautonews > data_only.sql
```

### 恢复

```bash
# 从 dump 文件恢复
docker-compose exec -T db pg_restore -U gan -d globalautonews backup.dump

# 从 SQL 文件恢复
docker-compose exec -T db psql -U gan globalautonews < backup.sql
```

---

## 如何添加新站点

### 方法 1: 通过 API

```bash
curl -X POST http://localhost:8000/api/sources \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Example Auto News",
    "domain": "example-auto.com",
    "url": "https://example-auto.com/news",
    "country": "US",
    "language": "en",
    "priority": "medium",
    "tier": 1
  }'
```

### 方法 2: 编辑 sources.yaml

1. 编辑 `config/sources.yaml`
2. 添加新站点：

```yaml
- name: Example Auto News
  domain: example-auto.com
  url: https://example-auto.com/news
  country: US
  language: en
  region: na
  tier: 1
  rendering: static
  priority: medium
```

3. 重新运行 seed 脚本：
   ```bash
   docker-compose exec crawler python scripts/seed_sources.py
   ```

### 方法 3: 通过候选审批

1. 系统会自动发现新站点（通过外链收集）
2. LLM 分析后标记为待审批
3. 在前端 CandidateQueue 页面审批通过

---

## 如何编写 Tier 2 适配器

Tier 2 适配器使用 YAML 配置文件定义页面结构。

### 步骤

1. **分析目标站点结构**
   - 使用浏览器开发者工具
   - 识别文章列表容器的 CSS 选择器
   - 识别文章内容容器的 CSS 选择器

2. **创建 YAML 文件**

在 `crawler/adapters/` 目录下创建文件，格式如：

```yaml
source_domain: example.com  # 目标域名
list_page:
  article_selector: "div.article-list > article"  # 文章列表容器
  link_selector: "a.article-title"                 # 文章链接
  link_attribute: "href"                           # 链接属性
  max_links: 20                                    # 最大链接数

article_page:
  title_selector: "h1.article-title"               # 标题
  content_selector: "div.article-content"          # 正文
  date_selector: "time.published-date"             # 日期
  date_format: "%Y-%m-%d"                          # 日期格式
  date_attribute: "datetime"                       # 从属性取值
  author_selector: "span.author-name"              # 作者
  image_selector: "div.article-content img:first"  # 题图
  remove_selectors:                                # 移除元素
    - "div.ad-container"
    - "div.related-articles"
    - "div.social-share"
    - "script"
    - "style"
```

3. **测试适配器**

```python
from crawler.extractors.adapter import AdapterExtractor

extractor = AdapterExtractor()
# 检查是否加载
print(extractor.has_adapter("example.com"))

# 测试提取
result = extractor.extract_article(html, url, "example.com")
print(result.title, result.content[:100])
```

4. **提交**

将 YAML 文件提交到仓库，系统会自动加载。

---

## 如何编写 Tier 3 定制爬虫

对于复杂的站点（如需要登录、JavaScript 渲染、分页等），需要编写定制爬虫。

### 步骤

1. **创建爬虫文件**

在 `crawler/custom/` 目录下创建 Python 文件：

```python
# crawler/custom/example_spider.py

import logging
from typing import List, Optional
from datetime import datetime

from crawler.engine.fetcher import Fetcher
from crawler.extractors.generic import GenericExtractor

logger = logging.getLogger("crawler.custom.example")


class ExampleSpider:
    """Example Auto News 定制爬虫"""

    def __init__(self, fetcher: Fetcher, extractor: GenericExtractor):
        self.fetcher = fetcher
        self.extractor = extractor

    async def crawl(self, base_url: str) -> List[dict]:
        """抓取所有文章"""
        articles = []

        # 1. 抓取列表页（可能需要翻页）
        page = 1
        while True:
            url = f"{base_url}/news?page={page}"
            result = await self.fetcher.fetch(url, rendering="dynamic")

            if not result.success:
                break

            # 2. 提取文章链接
            article_urls = self._extract_urls(result.html)
            if not article_urls:
                break

            # 3. 抓取每篇文章
            for article_url in article_urls:
                article = await self._crawl_article(article_url)
                if article:
                    articles.append(article)

            page += 1
            if page > 10:  # 限制最多 10 页
                break

        return articles

    def _extract_urls(self, html: str) -> List[str]:
        """提取文章 URL"""
        # 自定义提取逻辑
        pass

    async def _crawl_article(self, url: str) -> Optional[dict]:
        """抓取单篇文章"""
        result = await self.fetcher.fetch(url, rendering="dynamic")
        if not result.success:
            return None

        extract_result = self.extractor.extract(result.html, url)
        if not extract_result.success:
            return None

        return {
            "url": url,
            "title": extract_result.title,
            "content": extract_result.content,
            "published_at": extract_result.published_at,
        }
```

2. **在调度器中注册**

修改 `crawler/engine/scheduler.py`：

```python
from crawler.custom.example_spider import ExampleSpider

# 在 crawl_source 方法中
if source.domain == "example.com":
    spider = ExampleSpider(self.fetcher, self.extractor)
    articles = await spider.crawl(source.url)
```

---

## 定时任务清单

| 时间 | 任务 | 说明 |
|------|------|------|
| 每 60 秒 | 扫描待抓取站点 | 调度引擎主循环 |
| 每小时 | 外链收集 | T3.01 LinkCollector |
| 每天 02:00 | 站点健康检查 | T3.04 HealthManager |
| 每天 03:00 | 发布时间模式学习 | T5.02 |
| 每天 04:00 | 清理旧 crawl_logs | 保留 30 天 |
| 每周日 03:00 | paused 站点探活 | T3.04 |

### 配置定时任务

在 `crawler/main.py` 中配置 APScheduler：

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()

# 每小时外链收集
scheduler.add_job(
    lambda: link_collector.collect(hours=1),
    CronTrigger(minute=0)
)

# 每天 02:00 健康检查
scheduler.add_job(
    health_manager.run_daily_check,
    CronTrigger(hour=2, minute=0)
)

# 每周日 03:00 探活
scheduler.add_job(
    lambda: health_manager.run_weekly_probe(fetcher),
    CronTrigger(day_of_week="sun", hour=3, minute=0)
)

scheduler.start()
```

---

## 性能调优建议

### 数据库优化

1. **添加索引**（已包含在 init.sql）
   - `articles(url_hash)` - L1 去重
   - `articles(title_simhash)` - L2 去重
   - `articles(crawled_at)` - 时间范围查询
   - `sources(next_crawl_at)` - 调度查询

2. **定期清理**
   ```sql
   -- 清理 30 天前的日志
   DELETE FROM crawl_logs WHERE started_at < NOW() - INTERVAL '30 days';
   
   -- 清理重复文章（保留每个 cluster 的第一篇）
   UPDATE articles SET is_duplicate = TRUE 
   WHERE event_cluster_id IS NOT NULL 
   AND id NOT IN (
     SELECT MIN(id) FROM articles 
     WHERE event_cluster_id IS NOT NULL 
     GROUP BY event_cluster_id
   );
   ```

### 内存优化

1. **调整并发数**
   ```yaml
   # docker-compose.yml
   environment:
     - MAX_CONCURRENCY=3  # 从 5 降到 3
   ```

2. **调整 Playwright 并发**
   ```yaml
   environment:
     - PLAYWRIGHT_MAX_PAGES=1  # 从 2 降到 1
   ```

### 网络优化

1. **配置代理**（如需要）
   ```yaml
   environment:
     - HTTP_PROXY=http://proxy:8080
     - HTTPS_PROXY=http://proxy:8080
   ```

2. **调整超时**
   ```yaml
   environment:
     - FETCH_TIMEOUT=60  # 从 30 增加到 60
   ```
