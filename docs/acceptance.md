# GlobalAutoNews 验收测试文档

## 目录

1. [环境准备](#环境准备)
2. [Phase 1 验收 - 基础架构](#phase-1-验收---基础架构)
3. [Phase 2 验收 - 核心功能](#phase-2-验收---核心功能)
4. [Phase 3 验收 - 自增长系统](#phase-3-验收---自增长系统)
5. [Phase 4 验收 - 翻译与适配器](#phase-4-验收---翻译与适配器)
6. [Phase 5 验收 - 智能优化](#phase-5-验收---智能优化)
7. [端到端验收](#端到端验收)
8. [性能验收](#性能验收)

---

## 环境准备

### 启动系统

```bash
# 1. 进入项目目录
cd /Users/apple/Desktop/globalautonews

# 2. 启动所有服务
docker-compose up -d

# 3. 等待服务启动（约 30 秒）
sleep 30

# 4. 检查服务状态
docker-compose ps
```

### 验证服务运行

```bash
# 检查 API 健康状态
curl http://localhost:8000/api/health

# 预期输出：
# {"status":"healthy","version":"0.1.0"}
```

---

## Phase 1 验收 - 基础架构

### T1.01 - 项目骨架 + Docker Compose

**验收步骤：**
```bash
# 1. 检查目录结构
ls -la /Users/apple/Desktop/globalautonews/

# 预期目录：
# crawler/  api/  web/  shared/  config/  db/  scripts/  docs/

# 2. 检查 Docker 服务
docker-compose ps

# 预期服务：db, redis, crawler, api, web

# 3. 检查配置文件
cat config/settings.yaml
cat .env
```

**验收标准：** ✅ 所有目录和配置文件存在，Docker 服务正常运行

---

### T1.02 - 数据库 Schema

**验收步骤：**
```bash
# 连接数据库
docker-compose exec db psql -U gan -d globalautonews

# 执行 SQL 检查表
\dt

# 预期表：
# sources, articles, event_clusters, source_candidates, crawl_logs

# 检查索引
\di

# 检查字段
\d articles
\d sources

# 退出
\q
```

**验收标准：** ✅ 5 张表存在，索引正确，字段完整

---

### T1.03 - Python 数据模型

**验收步骤：**
```bash
# 检查模型文件
cat shared/models.py | head -50

# 测试导入
docker-compose exec crawler python -c "from shared.models import Source, Article; print('Models OK')"
```

**验收标准：** ✅ 模型文件存在，导入无错误

---

### T1.04 - 站点规范化

**验收步骤：**
```bash
# 检查 sources.yaml
wc -l config/sources.yaml

# 预期：约 200 行（199 个站点）

# 随机查看几个站点
grep -A2 "Toyota" config/sources.yaml
grep -A2 "BMW" config/sources.yaml
```

**验收标准：** ✅ 199 个汽车站点在 YAML 中，格式正确

---

### T1.05 - 种子脚本

**验收步骤：**
```bash
# 运行种子脚本
docker-compose exec crawler python scripts/seed_sources.py

# 检查数据库中的站点数量
docker-compose exec db psql -U gan -d globalautonews -c "SELECT COUNT(*) FROM sources;"

# 预期输出：199
```

**验收标准：** ✅ 199 个站点成功导入数据库

---

### T1.06 - HTTP 抓取器

**验收步骤：**
```bash
# 测试抓取
docker-compose exec crawler python -c "
import asyncio
from crawler.engine.fetcher import Fetcher

async def test():
    f = Fetcher()
    result = await f.fetch('https://www.autoblog.com/')
    print(f'Status: {result.status_code}')
    print(f'Content length: {result.content_length}')
    await f.close()

asyncio.run(test())
"
```

**验收标准：** ✅ 能成功抓取页面，返回状态码 200

---

### T1.07 - RSS 处理器

**验收步骤：**
```bash
# 测试 RSS 解析
docker-compose exec crawler python -c "
import asyncio
from crawler.engine.rss import RSSHandler

async def test():
    rss = RSSHandler()
    items = await rss.parse_feed('https://www.motor1.com/rss/news/')
    print(f'Found {len(items)} items')
    if items:
        print(f'First: {items[0].title}')

asyncio.run(test())
"
```

**验收标准：** ✅ 能解析 RSS feed，返回文章列表

---

### T1.08 - 通用提取器

**验收步骤：**
```bash
# 测试内容提取
docker-compose exec crawler python -c "
from crawler.extractors.generic import GenericExtractor

extractor = GenericExtractor()
html = '<html><body><h1>Test Title</h1><article>Test content here.</article></body></html>'
result = extractor.extract(html, 'https://example.com/test')
print(f'Success: {result.success}')
print(f'Title: {result.title}')
print(f'Content: {result.content}')
"
```

**验收标准：** ✅ 能提取标题和正文内容

---

### T1.09 - L1 + L2 去重

**验收步骤：**
```bash
# 测试 URL 哈希
docker-compose exec crawler python -c "
from crawler.pipeline.dedup import DedupPipeline

# L1: URL 哈希
hash1 = DedupPipeline.hash_url('https://example.com/article?id=1&utm_source=rss')
hash2 = DedupPipeline.hash_url('https://example.com/article?id=1')
print(f'L1 Same URL: {hash1 == hash2}')

# L2: SimHash
simhash1 = DedupPipeline.compute_simhash('Toyota announces new Camry 2026', 'en')
simhash2 = DedupPipeline.compute_simhash('Toyota reveals Camry 2026 model', 'en')
distance = DedupPipeline.hamming_distance(simhash1, simhash2)
print(f'L2 Hamming distance: {distance}')
"
```

**验收标准：** ✅ URL 标准化正确，相似标题 Hamming 距离 ≤ 3

---

### T1.10 - 调度引擎

**验收步骤：**
```bash
# 检查调度器日志
docker-compose logs crawler | grep -i "scheduler" | tail -10

# 检查是否有文章被抓取
docker-compose exec db psql -U gan -d globalautonews -c "SELECT COUNT(*) FROM articles;"
docker-compose exec db psql -U gan -d globalautonews -c "SELECT COUNT(*) FROM crawl_logs;"

# 等待几分钟后再次检查
sleep 60
docker-compose exec db psql -U gan -d globalautonews -c "SELECT COUNT(*) FROM articles;"
```

**验收标准：** ✅ 文章数量在增加，有 crawl_log 记录

---

### T1.11 - 基础 API

**验收步骤：**
```bash
# 测试 API 端点
curl http://localhost:8000/api/articles?limit=5 | python -m json.tool
curl http://localhost:8000/api/sources?limit=5 | python -m json.tool
curl http://localhost:8000/api/health

# 测试 Swagger 文档
# 在浏览器打开 http://localhost:8000/docs
```

**验收标准：** ✅ API 返回 JSON 数据，Swagger 文档可访问

---

## Phase 2 验收 - 核心功能

### T2.01 - Playwright 集成

**验收步骤：**
```bash
# 检查 Playwright 是否启用
docker-compose exec crawler python -c "
from crawler.engine.fetcher import Fetcher, PLAYWRIGHT_AVAILABLE
print(f'Playwright available: {PLAYWRIGHT_AVAILABLE}')
"

# 测试动态渲染
docker-compose exec crawler python -c "
import asyncio
from crawler.engine.fetcher import Fetcher

async def test():
    f = Fetcher()
    # 测试一个需要 JS 渲染的站点
    result = await f.fetch('https://www.carscoops.com/', rendering='dynamic')
    print(f'Status: {result.status_code}')
    print(f'Content length: {result.content_length}')
    await f.close()

asyncio.run(test())
"
```

**验收标准：** ✅ 动态渲染返回的内容比静态渲染多

---

### T2.02 - 自适应调频

**验收步骤：**
```bash
# 检查频率控制器
docker-compose exec crawler python -c "
from crawler.engine.frequency import FrequencyController

fc = FrequencyController()

# 测试发现率计算
rate = fc.calculate_discovery_rate(articles_new=5, articles_found=10)
print(f'Discovery rate: {rate}')

# 测试间隔调整
new_interval = fc.calculate_new_interval(current_interval=240, discovery_rate=0.6)
print(f'New interval (high rate): {new_interval} min')

new_interval = fc.calculate_new_interval(current_interval=240, discovery_rate=0.0)
print(f'New interval (zero rate): {new_interval} min')
"

# 检查数据库中的频率字段
docker-compose exec db psql -U gan -d globalautonews -c "SELECT id, name, crawl_interval_minutes, discovery_rate FROM sources LIMIT 5;"
```

**验收标准：** ✅ 高发现率缩短间隔，零发现率延长间隔

---

### T2.03 - 实体词典 + L3 去重

**验收步骤：**
```bash
# 检查实体词典
wc -l config/entities/brands.yaml
wc -l config/entities/models.yaml

# 预期：brands 至少 80 行，models 至少 50 行

# 测试实体提取
docker-compose exec crawler python -c "
from crawler.pipeline.entities import EntityExtractor

extractor = EntityExtractor()
result = extractor.extract(
    text='Toyota announced the new Camry 2026 with improved fuel efficiency.',
    title='Toyota Camry 2026'
)
print(f'Brands: {result[\"brands\"]}')
print(f'Models: {result[\"models\"]}')
"

# 检查 L3 去重
docker-compose exec crawler python -c "
from crawler.pipeline.dedup import DedupPipeline
print('L3 dedup implemented:', hasattr(DedupPipeline, '_check_l3'))
"
```

**验收标准：** ✅ 品牌词典 ≥ 80 个，实体提取正确识别品牌和车型

---

### T2.04 - EmbeddingGemma + L4 去重

**验收步骤：**
```bash
# 检查嵌入生成器
docker-compose exec crawler python -c "
from crawler.pipeline.embeddings import EmbeddingGenerator, SENTENCE_TRANSFORMERS_AVAILABLE
print(f'Sentence transformers available: {SENTENCE_TRANSFORMERS_AVAILABLE}')

gen = EmbeddingGenerator()
print(f'Generator available: {gen.is_available()}')
"

# 测试嵌入生成
docker-compose exec crawler python -c "
from crawler.pipeline.embeddings import EmbeddingGenerator
import numpy as np

gen = EmbeddingGenerator(mode='local')
if gen.is_available():
    emb = gen.generate('Toyota announces new electric vehicle')
    print(f'Embedding shape: {np.array(emb).shape}')
else:
    print('Local mode not available, using API mode')
"

# 检查 L4 去重
docker-compose exec db psql -U gan -d globalautonews -c "SELECT COUNT(*) FROM articles WHERE embedding IS NOT NULL;"
```

**验收标准：** ✅ 嵌入向量生成成功，L4 去重逻辑存在

---

### T2.05 - 事件聚类

**验收步骤：**
```bash
# 检查事件聚类
docker-compose exec db psql -U gan -d globalautonews -c "SELECT COUNT(*) FROM event_clusters;"
docker-compose exec db psql -U gan -d globalautonews -c "SELECT id, article_count, importance_score FROM event_clusters ORDER BY importance_score DESC LIMIT 5;"

# 检查文章关联
docker-compose exec db psql -U gan -d globalautonews -c "SELECT COUNT(*) FROM articles WHERE event_cluster_id IS NOT NULL;"
```

**验收标准：** ✅ 有 event_cluster 记录，文章关联到集群

---

### T2.06 - Vue.js 项目

**验收步骤：**
```bash
# 检查前端目录
ls -la web/src/views/

# 预期文件：
# NewsFeed.vue  EventDetail.vue  SourceList.vue  CandidateQueue.vue  Dashboard.vue

# 检查路由
cat web/src/router/index.js

# 在浏览器打开 http://localhost:80
```

**验收标准：** ✅ 前端页面可访问，路由配置正确

---

### T2.07 - NewsFeed 页面

**验收步骤：**
```bash
# 在浏览器打开 http://localhost:80/
# 检查：
# 1. 文章列表是否显示
# 2. 筛选面板是否工作
# 3. 搜索功能是否正常
```

**验收标准：** ✅ 文章列表显示，筛选和搜索功能正常

---

### T2.08 - Dashboard 页面

**验收步骤：**
```bash
# 在浏览器打开 http://localhost:80/dashboard
# 检查：
# 1. 统计卡片是否显示数据
# 2. 健康矩阵是否显示
# 3. 待修复站点列表
```

**验收标准：** ✅ Dashboard 显示统计数据和健康状态

---

### T2.09 - Nginx 反向代理

**验收步骤：**
```bash
# 测试 API 代理
curl http://localhost/api/health

# 测试静态文件
curl -I http://localhost/

# 检查 Nginx 配置
docker-compose exec web cat /etc/nginx/conf.d/default.conf
```

**验收标准：** ✅ API 通过 /api 代理，静态文件正常服务

---

## Phase 3 验收 - 自增长系统

### T3.01 - 外链收集器

**验收步骤：**
```bash
# 检查候选源
docker-compose exec db psql -U gan -d globalautonews -c "SELECT COUNT(*) FROM source_candidates;"
docker-compose exec db psql -U gan -d globalautonews -c "SELECT domain, mention_count FROM source_candidates ORDER BY mention_count DESC LIMIT 10;"
```

**验收标准：** ✅ source_candidates 表有数据，mention_count 正确递增

---

### T3.02 - LLM 新源分析器

**验收步骤：**
```bash
# 检查分析结果
docker-compose exec db psql -U gan -d globalautonews -c "SELECT domain, status, auto_analysis->>'is_automotive' as is_auto FROM source_candidates WHERE auto_analysis IS NOT NULL LIMIT 10;"
```

**验收标准：** ✅ auto_analysis 字段有 JSON 数据，非汽车站点被拒绝

---

### T3.03 - 候选源审批 API + UI

**验收步骤：**
```bash
# 测试审批 API
curl http://localhost:8000/api/candidates | python -m json.tool

# 在浏览器打开 http://localhost:80/candidates
# 测试批准/拒绝功能
```

**验收标准：** ✅ 审批列表显示，批准后 sources 表有新记录

---

### T3.04 - 站点健康生命周期

**验收步骤：**
```bash
# 检查站点状态分布
docker-compose exec db psql -U gan -d globalautonews -c "SELECT status, COUNT(*) FROM sources GROUP BY status;"

# 检查连续错误
docker-compose exec db psql -U gan -d globalautonews -c "SELECT id, name, status, consecutive_errors FROM sources WHERE consecutive_errors > 0 ORDER BY consecutive_errors DESC LIMIT 10;"
```

**验收标准：** ✅ 有 degraded/paused 状态的站点，连续错误计数正确

---

### T3.05 - 待修复站点队列

**验收步骤：**
```bash
# 测试待修复 API
curl http://localhost:8000/api/sources/needs-repair | python -m json.tool

# 在浏览器检查 Dashboard 的待修复面板
```

**验收标准：** ✅ extract_empty 的站点在待修复列表中

---

## Phase 4 验收 - 翻译与适配器

### T4.01 - 按需翻译服务

**验收步骤：**
```bash
# 获取一篇文章 ID
ARTICLE_ID=$(docker-compose exec db psql -U gan -d globalautonews -t -c "SELECT id FROM articles LIMIT 1;" | tr -d ' ')

# 测试翻译
curl -X POST "http://localhost:8000/api/articles/$ARTICLE_ID/translate" \
  -H "Content-Type: application/json" \
  -d '{"target_language": "zh"}' | python -m json.tool

# 检查数据库
docker-compose exec db psql -U gan -d globalautonews -c "SELECT title, title_zh FROM articles WHERE id = $ARTICLE_ID;"
```

**验收标准：** ✅ 翻译成功，title_zh 字段有值

---

### T4.02 - EventDetail 页面

**验收步骤：**
```bash
# 获取一个事件 ID
EVENT_ID=$(docker-compose exec db psql -U gan -d globalautonews -t -c "SELECT id FROM event_clusters LIMIT 1;" | tr -d ' ')

# 测试事件 API
curl "http://localhost:8000/api/events/$EVENT_ID" | python -m json.tool

# 在浏览器打开 http://localhost:80/event/$EVENT_ID
```

**验收标准：** ✅ 事件详情显示所有关联文章，翻译按钮可用

---

### T4.03 - Tier 2 适配器引擎

**验收步骤：**
```bash
# 检查适配器
ls -la crawler/adapters/

# 测试适配器
docker-compose exec crawler python -c "
from crawler.extractors.adapter import AdapterExtractor

extractor = AdapterExtractor()
print(f'Loaded adapters: {extractor.get_loaded_adapters()}')
print(f'Has car1.hk: {extractor.has_adapter(\"car1.hk\")}')
"
```

**验收标准：** ✅ 适配器正确加载，YAML 配置可解析

---

## Phase 5 验收 - 智能优化

### T5.01 - 自动模板生成

**验收步骤：**
```bash
# 检查模板生成器
docker-compose exec crawler python -c "
from crawler.discovery.template_generator import TemplateGenerator
print('Template generator available')
"
```

**验收标准：** ✅ 模板生成器模块存在

---

### T5.02 - 发布时间模式学习

**验收步骤：**
```bash
# 测试频率控制器的模式学习
docker-compose exec crawler python -c "
from crawler.engine.frequency import FrequencyController

fc = FrequencyController()

# 测试是否应该抓取
should, reason = fc.should_crawl_now(
    publish_hours={9: 10, 10: 15, 14: 8, 20: 2},
    publish_weekdays={0: 20, 1: 25, 2: 22, 3: 18, 4: 15, 5: 5, 6: 3},
    current_hour=9,
    current_weekday=1
)
print(f'Should crawl: {should}, Reason: {reason}')

# 测试优化间隔
interval = fc.get_optimized_interval(
    base_interval=240,
    publish_hours={9: 10, 10: 15, 14: 8},
    current_hour=10
)
print(f'Optimized interval: {interval} min')
"
```

**验收标准：** ✅ 高峰时段缩短间隔，低谷时段跳过抓取

---

### T5.03 - 运维文档

**验收步骤：**
```bash
# 检查文档
ls -la docs/operations.md

# 查看内容
head -50 docs/operations.md
```

**验收标准：** ✅ 运维文档存在，包含部署步骤和故障排查

---

## 端到端验收

### 完整抓取流程

```bash
# 1. 重置数据库（可选）
docker-compose exec db psql -U gan -d globalautonews -c "TRUNCATE articles, crawl_logs CASCADE;"

# 2. 等待抓取
echo "等待 5 分钟让系统抓取文章..."
sleep 300

# 3. 检查结果
echo "=== 抓取统计 ==="
docker-compose exec db psql -U gan -d globalautonews -c "SELECT COUNT(*) as total_articles FROM articles;"
docker-compose exec db psql -U gan -d globalautonews -c "SELECT COUNT(*) as total_clusters FROM event_clusters;"
docker-compose exec db psql -U gan -d globalautonews -c "SELECT COUNT(*) as total_sources FROM sources WHERE last_success_at IS NOT NULL;"

# 4. 检查去重效果
echo "=== 去重统计 ==="
docker-compose exec db psql -U gan -d globalautonews -c "SELECT is_duplicate, COUNT(*) FROM articles GROUP BY is_duplicate;"

# 5. 检查多语言覆盖
echo "=== 语言分布 ==="
docker-compose exec db psql -U gan -d globalautonews -c "SELECT language, COUNT(*) FROM articles GROUP BY language ORDER BY COUNT(*) DESC LIMIT 10;"
```

### 前端验证

```bash
echo "请在浏览器中验证以下页面："
echo "1. 新闻流: http://localhost:80/"
echo "2. 事件详情: http://localhost:80/event/1"
echo "3. 信息源: http://localhost:80/sources"
echo "4. 候选审批: http://localhost:80/candidates"
echo "5. Dashboard: http://localhost:80/dashboard"
echo ""
echo "API 文档: http://localhost:8000/docs"
```

---

## 性能验收

### 资源使用

```bash
# 检查 Docker 容器资源使用
docker stats --no-stream

# 预期：
# - db: < 512MB RAM
# - crawler: < 1GB RAM
# - api: < 256MB RAM
# - web: < 128MB RAM
```

### 抓取性能

```bash
# 检查抓取速度
docker-compose exec db psql -U gan -d globalautonews -c "
SELECT 
    DATE(started_at) as date,
    COUNT(*) as crawl_count,
    SUM(articles_new) as new_articles,
    AVG(response_time_ms) as avg_response_time
FROM crawl_logs
WHERE started_at > NOW() - INTERVAL '1 day'
GROUP BY DATE(started_at)
ORDER BY date DESC;
"
```

### API 响应时间

```bash
# 测试 API 响应时间
time curl -s http://localhost:8000/api/articles?limit=10 > /dev/null
time curl -s http://localhost:8000/api/sources > /dev/null
time curl -s http://localhost:8000/api/events > /dev/null

# 预期：每个请求 < 500ms
```

---

## 验收检查清单

### 功能验收

| 功能 | 状态 | 备注 |
|------|------|------|
| 199 个站点导入 | ☐ | |
| 文章抓取运行 | ☐ | |
| L1 URL 去重 | ☐ | |
| L2 SimHash 去重 | ☐ | |
| L3 实体去重 | ☐ | |
| L4 向量去重 | ☐ | |
| 事件聚类 | ☐ | |
| 自适应调频 | ☐ | |
| 健康生命周期 | ☐ | |
| 外链收集 | ☐ | |
| LLM 分析 | ☐ | |
| 候选审批 | ☐ | |
| 翻译服务 | ☐ | |
| Tier 2 适配器 | ☐ | |
| Vue.js 前端 | ☐ | |
| Dashboard | ☐ | |

### 性能验收

| 指标 | 目标 | 实际 | 状态 |
|------|------|------|------|
| 内存使用 (crawler) | < 1GB | | ☐ |
| API 响应时间 | < 500ms | | ☐ |
| 每小时抓取量 | > 1000 | | ☐ |
| 去重准确率 | > 90% | | ☐ |

### 文档验收

| 文档 | 状态 |
|------|------|
| 运维文档 | ☐ |
| API 文档 (Swagger) | ☐ |
| 代码注释 | ☐ |

---

## 验收结论

验收日期：_______________

验收人员：_______________

验收结果：☐ 通过  ☐ 不通过

备注：
_______________________________________________
_______________________________________________
_______________________________________________
