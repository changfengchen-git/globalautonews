# T3.01 — 外链收集器

## 任务目标
从已抓文章的 external_links 中收集候选新信息源。

## 前置依赖
- T1.08（提取器，提供 external_links 字段）

## 需要创建的文件
- `crawler/discovery/link_collector.py`

## 实现要求

1. **定时任务**：每小时执行一次
2. **逻辑**：
   - 扫描最近 24h 内新入库文章的 external_links
   - 提取域名，过滤黑名单域名（社交媒体、搜索引擎、CDN、已有 sources 的域名）
   - 保留包含汽车关键词的 URL：auto, car, motor, vehicle, ev, otomotif, automobile, etc.
   - 如果域名已在 source_candidates 表 → mention_count +1, 追加 discovered_from
   - 如果是新域名 → INSERT 到 source_candidates
   - 当 mention_count >= 5 → 标记为可分析（触发 T3.02 的 LLM 分析）

3. **关键词列表**（多语言汽车关键词）：
   ```python
   AUTO_KEYWORDS = {
       "auto", "car", "motor", "vehicle", "ev", "electric",
       "automobile", "automotive", "otomotif", "voiture",
       "carro", "coche", "wagen", "kuruma", "xe", "mobil",
   }
   ```

## 验收标准

1. ✅ 新发现的域名入库到 source_candidates
2. ✅ 重复发现的域名 mention_count 递增
3. ✅ 黑名单域名被正确过滤
4. ✅ 不包含已有的 sources 域名

---

# T3.02 — LLM 新源分析器

## 任务目标
对 mention_count >= 5 的候选站点调用 LLM 分析其是否为汽车新闻源。

## 前置依赖
- T3.01

## 需要创建的文件
- `crawler/discovery/analyzer.py`

## 实现要求

1. **触发条件**：source_candidates.mention_count >= 5 且 auto_analysis IS NULL
2. **分析流程**：
   a. 用 Fetcher 抓取候选站点首页
   b. 提取前 2000 字符文本
   c. 调用 GPT-4o-mini API，Prompt：
   ```
   分析以下网页内容，判断是否为汽车行业新闻站点。请用 JSON 格式回答：
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
   ```
   d. 解析 JSON 结果，存入 auto_analysis
   e. is_automotive=True 的保持 status='pending'，等待人工审批
   f. is_automotive=False 的自动 status='rejected'

3. **成本控制**：每天最多分析 20 个候选站点

## 验收标准

1. ✅ LLM 返回有效的 JSON 分析结果
2. ✅ 分析结果正确存入 source_candidates.auto_analysis
3. ✅ 非汽车站点被自动拒绝
4. ✅ 每日分析数量有上限控制

---

# T3.03 — 候选源审批 API + UI

## 任务目标
实现候选新源的审批 API 端点，以及 Vue.js 审批页面。

## 前置依赖
- T3.02, T2.06

## 实现要求

### API 端点（api/routes/candidates.py）
```
GET    /api/candidates                — 候选源列表（按 mention_count 排序）
GET    /api/candidates/{id}           — 候选源详情（含 auto_analysis）
POST   /api/candidates/{id}/approve   — 批准（创建 source 记录，状态设为 active）
POST   /api/candidates/{id}/reject    — 拒绝
```

### Vue.js 页面（CandidateQueue.vue）
- 卡片式审批界面
- 每张卡片显示：URL、域名、mention_count、LLM 分析结论（is_automotive, language, confidence）、discovered_from 的文章标题
- 批准/拒绝按钮
- 批准时可以编辑 name, country, language
- 批准后自动创建 Source 记录（tier=1, status=active）

## 验收标准

1. ✅ 审批列表正确展示
2. ✅ 批准后 sources 表中有新记录
3. ✅ 拒绝后 source_candidates.status = 'rejected'
4. ✅ 新批准的站点开始被调度引擎抓取

---

# T3.04 — 站点健康生命周期管理

## 任务目标
实现 active → degraded → paused → archived 的完整生命周期管理。

## 前置依赖
- T1.10（调度引擎）

## 需要创建的文件
- `crawler/engine/health.py`

## 实现要求

1. **状态转换逻辑**（在每次抓取后执行）：
   ```python
   def update_health(source, crawl_result):
       if crawl_result.success:
           source.status = 'active'
           source.consecutive_errors = 0
           source.days_without_new = 0 if crawl_result.articles_new > 0 else source.days_without_new
       else:
           source.consecutive_errors += 1
           if source.consecutive_errors >= 15 and source.status == 'degraded':
               source.status = 'paused'
               source.paused_at = now()
           elif source.consecutive_errors >= 5 and source.status == 'active':
               source.status = 'degraded'
               source.degraded_at = now()
   ```

2. **每日任务**（凌晨 2:00）：
   - 对所有 active 站点检查 days_without_new
   - 超过 30 天无新文章 → priority = 'low'
   - 超过 90 天无新文章 → status = 'archived'

3. **周检探活**（每周日凌晨 3:00）：
   - 对所有 paused 站点发起 HTTP HEAD 探测
   - 200 → 尝试完整抓取一次 → 成功则恢复 active

4. **爬虫失效检测**：
   - `last_error_type = 'extract_empty'` → 标记到一个"待修复"队列
   - 在 Dashboard 中高亮这些站点（T3.05）

## 验收标准

1. ✅ 连续错误 >= 5 的站点自动进入 degraded
2. ✅ degraded 站点抓取间隔变为原来 3 倍
3. ✅ 连续错误 >= 15 的 degraded 站点进入 paused
4. ✅ paused 站点不参与常规调度，但每周探活
5. ✅ 探活成功的站点恢复 active
6. ✅ 90 天无新文章自动归档

---

# T3.05 — 待修复站点队列 + Dashboard 集成

## 任务目标
在 Dashboard 中展示需要人工介入修复的站点（爬虫失效、需要升级提取器等）。

## 前置依赖
- T3.04, T2.08

## 实现要求

1. **API 新增端点**：
   ```
   GET /api/sources/needs-repair — 返回 last_error_type='extract_empty' 的站点列表
   ```

2. **Dashboard 中新增区域**：
   - "需要修复" 面板：列出 extract_empty 的站点
   - 每个站点显示：名称、域名、错误次数、上次成功时间
   - 提供"手动重试"按钮和"升级到 Tier 2"按钮

## 验收标准

1. ✅ 待修复站点列表正确展示
2. ✅ 手动重试触发一次立即抓取
