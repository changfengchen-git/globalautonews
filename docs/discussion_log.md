# GlobalAutoNews 方案设计讨论记录

> 项目：全球汽车行业新闻监控与聚合系统
> 创建时间：2026-04-15
> 状态：方案讨论阶段

---

## 一、项目概述

### 1.1 核心目标
- 对 200+ 全球汽车行业新闻站点进行 7×24 小时不间断抓取监控
- 抓取内容进行跨语种去重与事件聚合
- 按语种和国家进行区分和筛选
- 具备"自我生长"能力：从已抓内容中自动发现新信息源

### 1.2 站点覆盖（根据 sites0415 文件统计）

| 区域 | 站点数量（约） | 语言 | 代表站点 |
|------|-------------|------|---------|
| 印度（印地语区） | ~10 | hi, en | abplive, navbharattimes, carwale |
| 香港 | ~9 | zh-HK, en | car1.hk, hk01, hkev.org |
| 美国 | ~13 | en | motor1, caranddriver, jalopnik |
| 印尼 | ~12 | id | detik, kompas, gridoto |
| 巴西 | ~14 | pt | globo, uol, motor1.br |
| 巴基斯坦 | ~9 | en, ur | pakwheels, propakistani |
| 俄罗斯 | ~9 | ru | autonews.ru, zr.ru |
| 墨西哥 | ~9 | es | motorpasion.mx, milenio |
| 日本 | ~10 | ja | carview.co.jp, kuruma-news |
| 越南 | ~14 | vi | vnexpress, xehay |
| 德国 | ~10 | de | autobild, adac |
| 土耳其 | ~6 | tr | motor1.tr, ntv.com.tr |
| 泰国 | ~9 | th, en | bangkokpost, autospinn |
| 英国 | ~10 | en | autocar, topgear, pistonheads |
| 意大利 | ~18 | it | quattroruote, motor1.it |
| 韩国 | ~9 | ko | autotribune.co.kr |
| 西班牙/阿根廷 | ~14 | es | motor.es, diariomotor |
| 沙特/中东 | ~17 | ar, en | saudiauto, yallamotor |
| 马来西亚 | ~10 | en, ms | paultan.org, carlist.my |
| 澳大利亚 | ~9 | en | carexpert, drive.com.au |
| 南非 | ~4 | en | topauto.co.za, carmag.co.za |
| 菲律宾 | ~1 | en, tl | carnewsphilippines (Facebook) |

**注意事项**：
- 部分站点在多个国家区域下重复出现（如 motor1.com, motorsport.com, caranddriver.com）
- 格式不统一：部分为完整URL、部分仅为域名
- 有1个 Facebook 页面（菲律宾），需要特殊处理

---

## 二、第一轮讨论：核心需求确认（2026-04-15）

### 问题与回答

#### Q1: 基础设施约束
**回答**：
- VPS 最高配置：4GB 内存 + 50GB 存储
- 原本无计划用 Mac Mini 做计算
- 倾向使用外部 LLM API（如 OpenAI、Claude 等）
- 预估每日新增约 1000 条（200站 × 50%活跃 × 10条/站）
- Mac Mini 在国内，部分站点需要翻墙，VPS 在海外更方便
- **开放态度**：如果 API 成本过高，愿意考虑 Mac Mini 分担计算

#### Q2: 抓取深度与频率
**回答**：
- ✅ 需要抓取正文全文
- ✅ 正文解析需要多种方式（通用解析器 + 定制化爬虫）
- ✅ 自适应抓取频率：不是固定间隔，而是学习每个站点的发布习惯
- ✅ 需要处理 JavaScript 动态加载页面（需 Playwright/Puppeteer）

#### Q3: "自我生长"能力
**回答**：
- 首要方式：从已抓文章中的外部链接发现新源
- 补充方式：搜索引擎验证（用户认为是个好主意）
- 新源标准：必须有独家信息，或者信息时效性不差
- ✅ 需要人工审批环节（候选源审批队列）
- 首次爬虫方案确认在 AI 编程工具中完成（LLM 辅助爬虫生成）
- 能模板化的尽量模板化

#### Q4: 去重与内容处理
**回答**：
- ✅ 语义级别去重（不仅仅是标题匹配）
- ✅ 跨语种事件聚合（同一事件的多语种报道关联在一起）
- 保留原文可查看
- 对外展示时统一成一种语言（待确认：中文还是英文？）

#### Q5: 输出与使用场景
**回答**：
- ✅ Web UI：查看新闻、审批新信息源
- ✅ API 接口：供外部拉取或推送
- ✅ 爬虫健康状态监控（简单，非管理）
- ❌ 监控告警模块放到二期（且不应该只针对关键词）

#### Q6: 法律与反爬
**回答**：
- 愿意付费购买合法代理池服务
- 不使用非法手段（不黑别人系统）
- 不需要遵守 robots.txt

---

## 三、第二轮讨论：技术可行性深入分析（2026-04-15）

### 3.1 资源瓶颈分析：4GB VPS 的可行性

这是最关键的约束。下面逐项分析 4GB 内存的预算分配：

| 组件 | 最低内存需求 | 说明 |
|------|------------|------|
| 操作系统 | ~300MB | Linux 基础开销 |
| PostgreSQL | ~256-512MB | 含索引和缓存 |
| Playwright 浏览器实例 | ~200-400MB/个 | 最大的内存消耗者 |
| Python 爬虫调度器 | ~100-200MB | Celery/APScheduler |
| Web 应用 (FastAPI) | ~100-150MB | API + Web UI |
| Redis (队列/缓存) | ~50-100MB | 任务队列和缓存 |
| 系统预留 | ~200MB | 避免 OOM |
| **合计最低** | **~1.2-1.9GB** | 不含 Playwright |

**关键问题**：Playwright 是内存杀手。如果同时开 3 个浏览器实例就需要 600MB-1.2GB。

**可能的解决策略**：
1. Playwright 实例严格限制为 1-2 个并发，用完即释放
2. 优先使用 RSS/HTTP 请求方式，仅对 JS 渲染站点使用 Playwright
3. 对站点进行分级：静态站点用 requests + BeautifulSoup，动态站点用 Playwright

### 3.2 存储容量分析：50GB 的使用寿命

假设每日 1000 条文章：
- 每篇文章正文约 5-10KB
- 元数据约 1KB
- 向量嵌入约 6KB（1536维 float32）
- 每日增量：约 12-17MB
- 每月增量：约 360-510MB
- 每年增量：约 4.3-6.1GB

附加开销：
- PostgreSQL 索引：约占数据量的 30-50%
- 系统和应用程序：约 5-8GB
- 日志：需要定期清理

**结论**：50GB 可处理约 3-5 年的数据，可行。但需要定期归档老数据。

### 3.3 外部 API 成本估算

每日 1000 条文章的处理成本：

| API 用途 | 调用量/天 | 单次成本（约） | 日成本 | 月成本 |
|---------|----------|-------------|--------|--------|
| 文本嵌入 (OpenAI embedding) | 1000次 | $0.0001/1K tokens | ~$0.5 | ~$15 |
| 翻译 (DeepL/Google) | 1000次 | $20/1M 字符 | ~$1-2 | ~$30-60 |
| 语义去重比较 | ~5000次比较 | 嵌入向量余弦，本地计算 | $0 | $0 |
| LLM 摘要/分类 | 1000次 | $0.01/次(GPT-4o-mini) | ~$10 | ~$300 |
| LLM 新源分析 | ~50次 | $0.05/次 | ~$2.5 | ~$75 |
| **合计** | | | **~$14-15** | **~$420-450** |

**优化方向**：
- 嵌入使用小模型或本地模型可大幅降低成本
- 翻译可以延迟到用户查看时按需翻译
- LLM 摘要可用更便宜的模型或按需生成
- 分类可以用本地轻量模型替代

---

## 四、第二轮讨论结果：技术选型确认（2026-04-15）

### 已确认决策

| 编号 | 决策点 | 结论 |
|------|-------|------|
| 4.1 | 统一输出语言 | ✅ **中英双语**：英文为内部索引语言，中文为展示语言 |
| 4.2 | API 成本 | ✅ **级联过滤降低成本**：先用免费的关键词/指纹去重，仅对剩余内容用 API 嵌入 |
| 4.3 | Playwright 策略 | ✅ **先静态尝试，失败再动态**，并发限制 1-2 个实例 |
| 4.4 | 数据库选型 | ✅ **PostgreSQL + pgvector**，精细调优内存参数 |
| 4.5 | 部署方式 | ✅ **Docker Compose** |
| 4.6 | 站点列表整理 | ✅ 由 AI 根据语言自动识别国家归属，优先级以 Google 排名为初始值 |
| 4.7 | 爬虫架构 | ✅ **三级架构**：通用提取器 → 声明式适配器 → 定制 Python 爬虫 |
| 4.8 | 跨语种聚合 | ✅ **多语言嵌入模型**（multilingual-e5）直接跨语种比较 |
| 4.9 | 自我生长分期 | ✅ 三阶段渐进：外链收集→自动模板→LLM生成适配器 |

### 4.2 详细方案：级联去重（成本优化核心）

用户提出关键洞察：**先用不消耗 Token 的方式过滤，降低召回率换取准确率和低成本**。

最终设计为 4 级级联过滤：

| 级别 | 方法 | 成本 | 过滤效果 | 累计剩余 |
|------|------|------|---------|---------|
| L1 | URL 精确去重（哈希） | 免费 | ~20% 被过滤 | ~800条 |
| L2 | 标题指纹（SimHash/编辑距离） | 免费 | ~30% 被过滤 | ~560条 |
| L3 | 关键实体 + 时间窗口（品牌/车型/人名提取 + 24h窗口） | 免费 | ~20% 被过滤 | ~450条 |
| L4 | 多语言嵌入向量余弦相似度（跨语种去重） | API | 仅处理剩余约 300 条 | ~300条 |

**优化后月成本估算**：
- 嵌入 API（300条/天）：~$3/月
- LLM 新源分析（50条/天）：~$75/月
- 翻译（按需，用户查看时触发）：~$10-20/月
- **合计：~$90/月（约 ¥620）**

### 4.7 详细方案：三级爬虫架构

```
抓取请求
    │
    ▼
┌─────────────────────────────────────────┐
│  Tier 1: 通用提取器 (trafilatura)       │ ← 80% 站点可覆盖
│  自动检测正文区域，提取标题/正文/时间     │
│  零配置，对新站点天然友好                │
└─────────────┬───────────────────────────┘
              │ 提取失败或质量不达标
              ▼
┌─────────────────────────────────────────┐
│  Tier 2: 声明式适配器 (YAML 配置)       │ ← 15% 站点需要
│  定义 CSS 选择器、URL 模式、分页规则     │
│  LLM 可自动生成，人工可审核调整          │
└─────────────┬───────────────────────────┘
              │ 适配器也无法处理
              ▼
┌─────────────────────────────────────────┐
│  Tier 3: 定制 Python 爬虫               │ ← 5% 站点需要
│  处理 Facebook、登录墙、API 接口等       │
│  留成任务队列，系统大版本更新时开发       │
└─────────────────────────────────────────┘
```

---

## 五、第三轮讨论：收尾确认（2026-04-15）

### 5.1 技术栈（已确认）
- **语言**：Python 全栈
- **API 框架**：FastAPI
- **调度器**：APScheduler（替代 Celery + Redis，省内存）
- **浏览器引擎**：Playwright（仅动态站点使用）
- **数据库**：PostgreSQL + pgvector
- **部署**：Docker Compose
- **前端方案**：✅ **Vue.js SPA**

### 5.2 RSS 优先策略 → ✅ 已确认
对所有 200+ 站点先探测是否有 RSS 订阅源：
- 有 RSS → 用 RSS 获取文章列表（最轻量），再按需抓正文
- 无 RSS → 走 HTML 解析路径
- RSS 可减少 60-70% 的 HTML 解析和 Playwright 使用

### 5.3 代理池 → ✅ 初期不使用
初期不接代理池，遇到封 IP 再按需评估接入。成本待遇到时再调研。

### 5.4 自适应调度算法 → ✅ 已确认
- 初始：所有站点统一 4 小时一轮
- 运行 1-2 周后：统计"新文章发现率"
- 自动调频：高发现率→缩短间隔（最短 30 分钟），低发现率→拉长（最长 24 小时）
- 进阶：识别发布时间模式（工作日 vs 全天，高峰时段 vs 低谷）

### 5.5 API 成本补充说明
用户确认：新源分析量会随时间下降，成本会自然收敛。
- 初期（1-2个月）：~$50-75/月
- 稳定期（3个月后）：~$5-10/月
- **稳态月成本总计约 $15-25（¥100-170）**

### 5.6 项目推进方式 → ✅ 先出 implementation_plan.md 审核

---

## 六、讨论结论总览

所有关键决策已确认，讨论阶段完成。下一步：输出 `implementation_plan.md` 供审核。

| 维度 | 决策 |
|------|------|
| 基础设施 | 4GB VPS + 50GB 存储，Docker Compose 部署 |
| 语言 | Python 全栈 |
| 框架 | FastAPI + APScheduler + Playwright + Vue.js |
| 数据库 | PostgreSQL + pgvector |
| 爬虫架构 | 三级：通用提取器 → YAML适配器 → 定制Python |
| 抓取策略 | RSS 优先 → 静态 HTTP → Playwright 动态渲染 |
| 调度策略 | 自适应调频，学习站点发布习惯 |
| 去重 | 四级级联：URL哈希 → 标题指纹 → 实体+时间 → 多语言向量 |
| 跨语种 | multilingual-e5 嵌入向量，pgvector 本地计算 |
| 输出语言 | 中英双语（英文索引，中文展示） |
| 自我生长 | 三阶段：外链收集→自动模板→LLM适配器生成 |
| 代理池 | 初期不使用，按需接入 |
| 月成本 | 稳态 ~$15-25/月（API），VPS 另算 |
| 嵌入模型 | EmbeddingGemma (308M)，MRL 支持 256/512/768 维 |
| 图片策略 | 仅存 URL，前端引用原站图片 |
| 站点健康 | 生命周期管理：active→degraded→paused→archived |
| 2GB 支持 | docker-compose.lite.yml 精简模式 |

---

## 七、第四轮讨论：方案精化（2026-04-15）

### 7.1 嵌入模型选型更新
用户提问：本地 Gemma E4B 是否比 e5-small 更好？

**结论**：采用 **EmbeddingGemma (308M)**
- 基于 Gemma 3 架构，MTEB 同级别 SOTA
- 支持 MRL（Matryoshka Representation Learning），可按需截断为 768/512/256/128 维
- 比 e5-small 更强，但内存从 ~130MB 增加到 ~350MB
- 4GB VPS 可本地推理；2GB VPS 改用 API 调用
- 默认使用 256 维（省存储），精度不够可升至 512

### 7.2 2GB VPS 精简模式
用户确认希望支持 2GB VPS 场景。

**方案**：新增 `docker-compose.lite.yml` 覆盖文件
- PostgreSQL: shared_buffers=32MB，memory=256MB
- Crawler: 600MB，禁用 Playwright，禁用本地嵌入模型
- API: 128MB
- Web: 32MB
- 代价：损失 ~30-40% 动态站点覆盖，嵌入走 API（月增 ~$3）
- 可随时升级到 4GB，只需切换配置文件

### 7.3 图片存储策略
**结论**：仅存储图片 URL，不下载文件
- `image_url`：题图 URL
- `image_urls`：文中所有图片 URL 列表
- 前端通过 `<img src="原站URL">` 引用
- 原站图片失效时显示占位图
- 后期如需持久化可接入 Cloudflare R2（免费 10GB/月）
- 节省存储：每日 200MB → 0MB

### 7.4 站点自动清理（生命周期管理）
用户提出关键问题：站点抓不到可能是爬虫失效而非站点停更。

**设计方案**：五状态生命周期
```
active → (连续错误>=5) → degraded → (连续错误>=15) → paused → (90天) → archived
```

**错误分类**：
1. HTTP 错误 → 站点问题/反爬 → degraded → paused 流程
2. HTTP 200 但 0 文章 → 爬虫失效 → 待修复队列 + Dashboard 高亮
3. 有文章但无新文章 7 天 → 低频更新 → 拉长间隔
4. 无新文章 30 天 → 可能停更 → low priority
5. 无新文章 90 天 → 自动归档

**恢复机制**：
- 周检探活：每周日对 paused 站点 HTTP HEAD 检测
- 人工恢复：Dashboard 中可手动恢复任何状态

---

## 八、方案状态

✅ 所有讨论完成，`implementation_plan.md` 已更新为第二版，包含 11 个 Component。
✅ 用户已审核批准。
✅ 已拆分为 31 个可独立执行的开发任务（5 个 Phase）。

### 任务文档清单（docs/tasks/）
| 文件 | 内容 |
|------|------|
| `README.md` | 任务总览、依赖关系、技术栈速查 |
| `T1.01_project_skeleton.md` | 项目骨架 + Docker Compose |
| `T1.02_database_schema.md` | PostgreSQL 完整 DDL（5张表） |
| `T1.03_python_models.md` | SQLAlchemy ORM 模型 + DB 连接 |
| `T1.04_sites_normalization.md` | 200+站点列表转 YAML 的详细规则 |
| `T1.05_seed_sources.md` | YAML→数据库导入脚本 |
| `T1.06_http_fetcher.md` | HTTP 抓取器（UA轮换/编码/重试） |
| `T1.07_rss_handler.md` | RSS 探测与解析 |
| `T1.08_generic_extractor.md` | Tier 1 通用提取器 |
| `T1.09_dedup_l1_l2.md` | L1+L2 去重管线 |
| `T1.10_scheduler.md` | APScheduler 调度引擎 |
| `T1.11_basic_api.md` | FastAPI 基础 API |
| `T2_phase2_all.md` | Phase 2 全部任务（9个） |
| `T3_phase3_all.md` | Phase 3 全部任务（5个） |
| `T4_T5_phase4_5.md` | Phase 4-5 全部任务（6个） |

### 配套文档
| 文件 | 用途 |
|------|------|
| `docs/AI_CODING_GUIDE.md` | AI 编程工具使用指南 |
| `docs/discussion_log.md` | 设计讨论记录 |

下一步：按 T1.01 → T1.02 → ... 顺序交给 AI 编程工具执行。

---

## 七、功能优化讨论（2026-04-17）

### 7.1 优化需求清单

用户提出以下7项优化需求：

| 序号 | 需求 | 状态 |
|-----|------|-----|
| 1 | 增量抓取：首次抓30天，后续只抓新内容 | ✅ 已完成 |
| 2 | 新闻类型过滤：排除隐私协议等非新闻页面 | ✅ 已完成 |
| 3 | 三时区时间存储：本地/UTC/北京时间 | ✅ 已完成 |
| 4 | 免费翻译方案：MyMemory API + 批量翻译 | ✅ 已完成 |
| 5 | 修复筛选bug：前端参数名与后端匹配 | ✅ 已完成 |
| 6 | 翻页功能：从无限加载改为标准分页 | ✅ 已完成 |
| 7 | 站点统计：累计文章数 + 24小时文章数 | ✅ 已完成 |

### 7.2 技术实现要点

#### 7.2.1 增量抓取逻辑
- 位置：`crawler/engine/scheduler.py`
- 首次抓取：`last_crawl_at` 为 None 时，阈值 = now - 30天
- 后续抓取：阈值 = `last_crawl_at` - 1小时（留余量）
- RSS 和 HTML 抓取都应用时间过滤

#### 7.2.2 新闻类型过滤
- 位置：`crawler/extractors/generic.py`
- URL路径过滤：排除 /privacy, /about, /contact, /login 等
- 标题关键词过滤：排除 "Privacy Policy", "Terms of Service" 等
- 内容长度检查：小于100字符的页面跳过

#### 7.2.3 三时区时间存储
- 数据库新增字段：`published_at_local`, `published_at_beijing`
- 时区映射：40+国家代码到时区的映射表
- 工具函数：`convert_to_three_times()` 在 `scheduler.py` 中

#### 7.2.4 免费翻译方案
- 位置：`api/services/translate.py`
- MyMemory API：免费每天5000字符
- 批量翻译：合并多条文本用分隔符，翻译后再分割
- 优先级：DeepL > MyMemory > Google > Mock

#### 7.2.5 筛选bug修复
- 前端参数：`languages` → `language`, `countries` → `country`
- 后端只支持单选，前端取第一个值

#### 7.2.6 翻页功能
- 前端：`NewsFeed.vue` 从无限加载改为标准分页
- 每页20条，显示页码、总数、上一页/下一页按钮

#### 7.2.7 站点统计
- 累计文章数：`SELECT COUNT(*) FROM articles WHERE source_id = ? AND is_duplicate = FALSE`
- 24小时文章数：`SELECT COUNT(*) FROM articles WHERE source_id = ? AND crawled_at >= NOW() - INTERVAL '24 hours'`
- 修复：`crawl_count` 从抓取次数改为累计文章数量

### 7.3 排序功能修复

**问题**：前端使用客户端排序，只对当前页有效

**解决方案**：
- 后端API添加 `sort_by` 和 `sort_order` 参数
- 前端改为服务端排序，点击表头重新请求API
- 支持排序字段：`id`, `name`, `crawl_count`, `consecutive_errors`, `crawl_interval_minutes`, `last_crawl_at`

### 7.4 Git提交记录

| Commit | 说明 |
|--------|------|
| `c84ac60` | feat: 优化爬虫和前端功能（7项优化） |
| `31242a6` | fix: 累计抓取改为累计文章数量 |
| `1a24f36` | fix: 信息源排序功能（服务端排序） |

### 7.5 待解决问题

1. **部分站点抓取失败**：可能与IP地址有关，上线VPS后需调试
2. **L3去重错误**：`decoding to str: need a bytes-like object` - 需进一步调查
3. **事件聚类错误**：`representative_article_id` 已修复，但需验证

---

*讨论记录更新时间：2026-04-17 16:30*
