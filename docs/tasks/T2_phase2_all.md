# T2.01 — Playwright 集成

## 任务目标
在 Fetcher 中集成 Playwright，对 JS 动态渲染的站点使用无头浏览器抓取。

## 前置依赖
- T1.06（HTTP 抓取器）

## 需要修改的文件
- `crawler/engine/fetcher.py`

## 实现要求

1. **在 Fetcher 类中添加 Playwright 支持**：
   - 通过环境变量 `PLAYWRIGHT_ENABLED` 控制是否启用（默认 true）
   - 使用 `playwright.async_api` 的异步 API
   - 全局维护一个 Browser 实例，按需启动（懒加载）
   - 使用 `asyncio.Semaphore(2)` 限制最多 2 个并发浏览器页面

2. **修改 `fetch()` 方法**：
   - 当 `rendering="dynamic"` 且 Playwright 已启用 → 使用 Playwright
   - 当 `rendering="dynamic"` 但 Playwright 未启用 → 回退静态抓取 + 警告日志
   - 当 `rendering="static"` → 不变，继续用 httpx

3. **Playwright 抓取逻辑**：
   ```python
   async def _fetch_dynamic(self, url: str) -> FetchResult:
       async with self._pw_semaphore:
           context = await self._browser.new_context(
               user_agent=self._get_random_ua(),
               viewport={"width": 1280, "height": 800},
               java_script_enabled=True,
           )
           page = await context.new_page()
           try:
               response = await page.goto(url, wait_until="networkidle", timeout=60000)
               html = await page.content()
               return FetchResult(url=url, status_code=response.status, html=html, ...)
           finally:
               await context.close()
   ```

4. **内存管理**：
   - 每次使用完立即关闭 context
   - 在 `close()` 方法中关闭 browser 实例
   - 如果 Playwright 启动失败（如 Chromium 未安装），降级为静态模式

5. **自动渲染模式检测**（可选增强）：
   - 如果静态抓取返回内容 < 500 字符，但 URL 看起来正常 → 自动尝试 Playwright 重试
   - 成功后将该 source 的 rendering 更新为 "dynamic"

## 验收标准

1. ✅ `rendering="dynamic"` 的站点可以成功抓取 JS 渲染内容
2. ✅ Playwright 并发不超过 2
3. ✅ Playwright 禁用时回退到静态模式
4. ✅ 关闭 Fetcher 时 Playwright 资源正确释放
5. ✅ 测试一个需要 JS 渲染的站点（如 carscoops.com）对比静态/动态模式的抓取结果

---

# T2.02 — 自适应调频控制器

## 任务目标
实现根据站点发布习惯自动调整抓取频率的控制器。

## 前置依赖
- T1.10（调度引擎）

## 需要创建的文件
- `crawler/engine/frequency.py`

## 实现要求

1. **核心指标**：`discovery_rate = articles_new / articles_found`
2. **调频规则**（每次抓取后执行）：
   ```python
   if discovery_rate > 0.5:
       new_interval = max(30, current_interval * 0.7)     # 加速
   elif discovery_rate > 0.1:
       pass                                                 # 保持
   elif discovery_rate > 0:
       new_interval = min(1440, current_interval * 1.5)    # 减速
   else:  # == 0
       new_interval = min(1440, current_interval * 2)      # 大幅减速
   ```
3. **更新 Source 记录**：crawl_interval_minutes, next_crawl_at, discovery_rate, avg_articles_per_crawl
4. **发布时间模式记录**（Phase 5 的 T5.02 会用到）：统计每篇文章的发布小时和星期几，存入 publish_hours/publish_weekdays

## 验收标准

1. ✅ 高发现率站点间隔缩短
2. ✅ 零发现率站点间隔拉长
3. ✅ 间隔不低于 30 分钟，不超过 1440 分钟
4. ✅ publish_hours 统计正确

---

# T2.03 — 实体词典 + L3 去重

## 任务目标
创建汽车行业实体词典，实现 L3 实体+时间窗口去重。

## 前置依赖
- T1.09（去重管线，添加 L3 逻辑）

## 需要创建的文件

### 1. config/entities/brands.yaml
```yaml
# 汽车品牌多语言词典
# 格式: 英文名: [其他语言的名称]
Toyota: [丰田, トヨタ, 토요타, تويوتا]
Honda: [本田, ホンダ, 혼다]
BMW: [宝马, ビーエムダブリュー]
Mercedes-Benz: [奔驰, 梅赛德斯, メルセデス・ベンツ, 메르세데스-벤츠]
Volkswagen: [大众, フォルクスワーゲン, 폭스바겐]
# ... 至少 80 个品牌
```

### 2. config/entities/models.yaml
```yaml
# 常见车型词典
Model 3: [Model3]
Model Y: [ModelY]
Camry: [凯美瑞, カムリ, 캠리]
Corolla: [卡罗拉, カローラ, 코롤라]
# ... 至少 50 个热门车型
```

### 3. crawler/pipeline/entities.py
实体提取器：从文章标题和正文前 200 字中提取品牌、车型、组织名。

### 4. 在 crawler/pipeline/dedup.py 中添加 L3

L3 逻辑：
- 提取文章实体
- 查询同语种、24h 时间窗口内的文章
- 实体交集 >= 2 → 判定为同事件的不同报道
- 标记为重复，关联到同一个 event_cluster

## 验收标准

1. ✅ 品牌词典至少 80 个品牌
2. ✅ 实体提取可以正确识别 "Toyota announces new Camry" → entities: {brands: ["Toyota"], models: ["Camry"]}
3. ✅ L3 去重：相似实体+时间窗口内的文章被标记为重复

---

# T2.04 — EmbeddingGemma + L4 去重

## 任务目标
集成 EmbeddingGemma 嵌入模型，实现 L4 跨语种向量去重。

## 前置依赖
- T1.09（去重管线）
- T1.03（数据模型，articles.embedding 字段）

## 需要创建的文件
- `crawler/pipeline/embeddings.py`

## 实现要求

1. **双模式支持**（由环境变量 EMBEDDING_MODE 控制）：
   - `local`：加载 `google/embedding-gemma-3-308m` 模型，使用 sentence-transformers 本地推理
   - `api`：调用 OpenAI Embeddings API（或兼容接口）

2. **MRL 维度裁剪**：EmbeddingGemma 支持 MRL，默认输出 256 维（可配置）

3. **在 dedup.py 中添加 L4**：
   - 对通过 L1-L3 的文章计算嵌入向量
   - 使用 pgvector 查询相似文章：
     ```sql
     SELECT id, 1 - (embedding <=> :query_embedding) as similarity
     FROM articles
     WHERE embedding IS NOT NULL
     AND crawled_at > NOW() - INTERVAL '3 days'
     ORDER BY embedding <=> :query_embedding
     LIMIT 5
     ```
   - 相似度 > 0.85 → 判定为跨语种重复

4. **向量索引**：当 articles 表超过 1000 条时，创建 IVFFlat 索引：
   ```sql
   CREATE INDEX idx_articles_embedding ON articles
       USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
   ```

## 验收标准

1. ✅ 本地模式和 API 模式都可以生成嵌入向量
2. ✅ 同一事件的中英文报道余弦相似度 > 0.85
3. ✅ 不同事件的文章余弦相似度 < 0.7
4. ✅ 嵌入向量成功存入 articles.embedding
5. ✅ pgvector 相似搜索有结果返回

---

# T2.05 — 事件聚类

## 任务目标
实现跨语种事件聚类，将同一事件的不同报道关联到同一个 event_cluster。

## 前置依赖
- T2.04（L4 向量去重提供了相似度计算能力）

## 需要创建的文件
- `crawler/pipeline/clustering.py`

## 实现要求

1. **新文章入库时**的聚类逻辑：
   - 如果 L3/L4 判定与某篇文章重复 → 加入该文章的 event_cluster
   - 如果没有匹配 → 创建新的 event_cluster，当前文章为 representative
   
2. **更新 event_cluster**：
   - article_count +1
   - 更新 languages, countries 列表
   - 更新 language_count, country_count
   - importance_score = article_count * 0.4 + language_count * 0.3 + country_count * 0.3

3. **选择 representative**：language_count 最多的那个 cluster 的第一篇文章

## 验收标准

1. ✅ 同一事件的多篇报道关联到同一个 event_cluster
2. ✅ event_cluster 的统计数据正确
3. ✅ importance_score 正确计算

---

# T2.06 — Vue.js 项目搭建

## 任务目标
使用 Vite 初始化 Vue.js 3 前端项目，配置路由和基础布局。

## 前置依赖
- T1.11（API 基础端点）

## 需要创建的文件
在 `web/` 目录下初始化 Vue.js 项目。

## 实现要求

1. **使用 Vite 创建**：`npx -y create-vite@latest ./ --template vue`
2. **安装依赖**：vue-router, axios
3. **路由配置**（5 个页面）：
   - `/` → NewsFeed（新闻信息流）
   - `/event/:id` → EventDetail（事件详情）
   - `/sources` → SourceList（信息源列表）
   - `/candidates` → CandidateQueue（新源审批）
   - `/dashboard` → Dashboard（系统概览）
4. **基础布局**：
   - 顶部导航栏（Logo + 5 个页面链接）
   - 侧边栏或顶部筛选区域
   - 深色主题（暗色背景 #0f1117，卡片 #1a1d29）
   - 使用 Google Font: Inter
5. **API 封装**：`web/src/api/index.js`，封装 axios 调用
6. **Dockerfile**：多阶段构建（build + nginx）
7. **Nginx 配置**：反向代理 `/api` 到 api 容器

## 验收标准

1. ✅ `npm run dev` 可以运行
2. ✅ 可以访问所有 5 个路由（页面可以是空的）
3. ✅ 导航栏可以切换页面
4. ✅ 深色主题外观
5. ✅ API 请求可以代理到后端

---

# T2.07 — NewsFeed 页面

## 任务目标
实现新闻信息流页面，包含筛选、分页、文章卡片展示。

## 前置依赖
- T2.06（Vue.js 项目基础）

## 实现要求

1. **左侧筛选面板**（260px 宽）：
   - 语种筛选（checkbox 列表，显示各语种文章数量）
   - 国家筛选（checkbox 列表）
   - 信息源筛选（下拉选择）
   - 时间范围（日期选择器）
   - "显示重复文章" 开关

2. **中间文章列表**：
   - 文章卡片组件（ArticleCard）：
     - 题图缩略图（左侧，image_url 引用原站图片，失败显示占位图）
     - 标题（加粗，可点击跳转原文）
     - 摘要（excerpt，最多 2 行）
     - 元信息行：来源名称 | 国家旗帜emoji | 语种标签 | 时间
     - 如有 event_cluster → 显示 "🔗 N 篇报道" 链接
   - 无限滚动或分页按钮
   - 排序切换：最新 | 最重要（按 event importance_score）

3. **顶部搜索栏**：全文搜索输入框

4. **样式**：深色主题，卡片悬停有轻微发光效果，加载时有骨架屏

## 验收标准

1. ✅ 文章列表正确展示
2. ✅ 筛选器功能正常
3. ✅ 分页/无限滚动正常
4. ✅ 搜索功能正常
5. ✅ 图片加载失败时显示占位图
6. ✅ 响应式布局（移动端可用）

---

# T2.08 — Dashboard 页面

## 任务目标
系统概览页面，展示抓取统计、站点健康状态矩阵。

## 前置依赖
- T2.06, T1.11

## 实现要求

1. **统计卡片**（顶部 4 格）：
   - 今日新增文章数 / 去重数
   - 活跃信息源数 / 异常数
   - 覆盖语种数 / 国家数
   - 候选新源待审批数

2. **站点健康矩阵**：
   - 按国家分组的网格
   - 每个站点一个小色块：🟢active 🟡degraded 🔴paused ⚫archived
   - 鼠标悬停显示站点名称和最后抓取时间

3. **最近抓取日志**：
   - 最近 20 条 crawl_logs，显示站点名、状态、新文章数、耗时

## 验收标准

1. ✅ 统计数据实时显示
2. ✅ 健康矩阵颜色正确
3. ✅ 日志列表有数据

---

# T2.09 — Nginx 反向代理配置

## 任务目标
配置 Nginx 作为前端静态文件服务和 API 反向代理。

## 前置依赖
- T2.06

## 需要创建的文件
- `web/nginx.conf`

## 实现要求

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # Vue.js SPA 路由支持
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理
    location /api/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # 图片代理缓存（可选，减少原站请求）
    # location /proxy-image/ { ... }

    # Gzip 压缩
    gzip on;
    gzip_types text/plain application/json application/javascript text/css;
}
```

## 验收标准

1. ✅ `http://your-vps:80` 可以访问 Vue.js 前端
2. ✅ `http://your-vps:80/api/health` 正确代理到 API
3. ✅ Vue.js SPA 刷新页面不 404
