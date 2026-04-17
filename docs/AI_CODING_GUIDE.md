# GlobalAutoNews — AI 编程工具使用指南

> 本文档面向执行开发任务的 AI 编程工具（如 Cursor, Windsurf, Gemini Code Assist 等），
> 说明如何使用本项目的任务文档进行开发。

## 项目背景

GlobalAutoNews 是一个全球汽车新闻监控与聚合系统，核心功能：
- 7×24 不间断抓取 200+ 汽车新闻站点
- 四级级联去重（URL哈希→标题指纹→实体匹配→跨语种向量）
- 三级内容提取（通用提取→YAML适配器→定制Python）
- 自我生长（自动发现和添加新信息源）
- Web UI 浏览和管理

## 如何使用任务文档

### 1. 阅读顺序

先读以下文件了解全局：
1. `docs/tasks/README.md` — 任务总览和依赖关系
2. `implementation_plan.md` — 完整技术架构设计（如果可以访问）
3. `docs/discussion_log.md` — 设计讨论记录（了解决策背景）

### 2. 执行单个任务

每个任务文档都包含：
- **任务目标**：做什么
- **前置依赖**：需要先完成哪些任务
- **需要创建的文件**：完整的文件路径和代码规范
- **实现要求**：详细的技术规格
- **类接口定义**：方法签名和参数说明
- **验收标准**：如何验证任务完成

**执行步骤**：
1. 检查前置依赖是否已完成
2. 阅读完整任务文档
3. 按文档要求创建/修改文件
4. 运行验收标准中的测试
5. 确认全部通过

### 3. 执行顺序

严格按 Phase 顺序执行，同一 Phase 内按编号顺序：

```
Phase 1: T1.01 → T1.02 → T1.03 → T1.04(可并行) → T1.05 → T1.06 → T1.07 → T1.08 → T1.09 → T1.10 → T1.11
Phase 2: T2.01 → T2.02 → T2.03 → T2.04 → T2.05 → T2.06 → T2.07 → T2.08 → T2.09
Phase 3: T3.01 → T3.02 → T3.03 → T3.04 → T3.05
Phase 4: T4.01 → T4.02 → T4.03
Phase 5: T5.01 → T5.02 → T5.03
```

### 4. 每次会话的推荐 Prompt 模板

当你把某个任务交给 AI 编程工具时，使用以下 Prompt 模板：

```
请阅读以下任务文档并执行：

[粘贴任务文档全文]

项目根目录：/Users/apple/Desktop/globalautonews/
请严格按照文档要求创建文件，完成后运行验收标准中的测试。

注意事项：
- Python 3.11+，使用 type hints
- 使用 async/await 异步编程
- 所有文件 UTF-8 编码
- 不要修改其他任务已创建的文件，除非文档明确要求
- 如果遇到任何依赖问题，请说明而不是跳过
```

## 任务文档清单

```
docs/tasks/
├── README.md                    # 任务总览（依赖关系图 + 技术栈速查）
│
├── T1.01_project_skeleton.md    # 项目骨架 + Docker Compose
├── T1.02_database_schema.md     # PostgreSQL 数据库 Schema（5张表完整DDL）
├── T1.03_python_models.md       # SQLAlchemy ORM 模型 + 数据库连接
├── T1.04_sites_normalization.md # 200+站点列表规范化为YAML
├── T1.05_seed_sources.md        # YAML→数据库导入脚本
├── T1.06_http_fetcher.md        # 异步HTTP抓取器（UA轮换+编码检测+重试）
├── T1.07_rss_handler.md         # RSS探测与解析
├── T1.08_generic_extractor.md   # Tier1通用提取器（trafilatura）
├── T1.09_dedup_l1_l2.md         # L1 URL哈希 + L2 SimHash 去重
├── T1.10_scheduler.md           # 核心调度引擎（APScheduler）
├── T1.11_basic_api.md           # FastAPI 基础API端点
│
├── T2_phase2_all.md             # Phase 2 全部9个任务（Playwright/调频/L3L4/Vue.js）
├── T3_phase3_all.md             # Phase 3 全部5个任务（自我生长/健康管理）
└── T4_T5_phase4_5.md            # Phase 4-5 全部6个任务（翻译/适配器/优化）
```

## 关键设计约束

在开发过程中请时刻注意以下约束：

### 内存约束（4GB VPS）
| 容器 | 内存上限 | 注意事项 |
|------|---------|---------|
| PostgreSQL | 512MB | shared_buffers=128MB |
| Crawler | 1536MB | 含 Playwright + EmbeddingGemma |
| API | 256MB | |
| Nginx | 64MB | |

### 代码规范
- 所有异步函数使用 `async def`
- 数据库操作使用 SQLAlchemy 2.0 async 模式
- 日志使用 Python logging，logger 名称为 `"crawler.xxx"` 或 `"api.xxx"`
- 配置从 `config/settings.yaml` 或环境变量读取
- 错误不上抛导致进程崩溃，使用 try/except 保护

### 共享代码
`shared/` 目录包含 Crawler 和 API 共用的代码：
- `shared/database.py` — 数据库连接
- `shared/models.py` — ORM 模型

两个服务通过 Docker volumes 挂载 `./shared:/app/shared`

### 数据库表结构
表已经由 `db/init.sql` 创建（T1.02），Python 代码中不要使用 `Base.metadata.create_all()`。
ORM 模型（T1.03）必须与 init.sql 精确对应。

---

## 文档结构说明

### 为什么 Phase 1 是独立文件，Phase 2-5 是合并文件？

**Phase 1（11 个独立文件）**是整个系统的基础，后续所有功能都依赖它。每个任务都写了：
- 完整的代码规范（类接口、方法签名、数据类定义）
- 数据库完整 DDL（含约束和索引）
- 精确的验收测试代码（可直接运行的 Python 代码片段）
- 详细的实现算法（如 SimHash 分词规则、URL 标准化规则、质量评分公式）

**Phase 2-5（3 个合并文件）**的每个任务依赖 Phase 1 建立的约定和接口，所以只定义新增的功能逻辑，不需要重复说明基础架构。每个任务之间用 `---` 分隔，按编号排列，内部仍然包含完整的实现要求和验收标准。

### 推荐的工作流程

```
第一次会话：
  1. 让 AI 工具阅读 docs/AI_CODING_GUIDE.md（本文档）
  2. 让 AI 工具阅读 docs/tasks/README.md（了解全局任务列表）
  3. 开始执行 T1.01

每次后续会话：
  1. 告知 AI 工具"项目根目录是 /Users/apple/Desktop/globalautonews/"
  2. 粘贴当前要执行的任务文档全文
  3. 如果任务涉及修改 Phase 1 已创建的文件，提醒 AI 工具先阅读该文件的当前内容
  4. 完成后运行验收测试
```

### 跨任务引用关系

有些任务会修改前面任务创建的文件，这些在任务文档中会明确标注。常见的修改关系：

| 被修改的文件 | 创建于 | 后续被修改于 |
|-------------|--------|------------|
| `crawler/main.py` | T1.01（骨架） | T1.10（完整实现） |
| `crawler/pipeline/dedup.py` | T1.09（L1+L2） | T2.03（加L3）、T2.04（加L4） |
| `crawler/engine/fetcher.py` | T1.06（HTTP） | T2.01（加 Playwright） |
| `api/main.py` | T1.01（骨架） | T1.11（注册路由） |
| `docker-compose.yml` | T1.01 | T1.03（加 shared volume） |

### 如果某个任务执行失败

1. **依赖缺失**：检查前置任务是否已完成，检查对应文件是否存在
2. **接口不匹配**：检查被引用文件的实际内容是否与任务文档中描述的接口一致
3. **环境问题**：确保 Docker、Python 3.11+、Node.js 18+ 已安装
4. **数据库问题**：确保 PostgreSQL 容器已启动且 init.sql 已执行

遇到无法解决的问题，记录错误信息和当前状态，在下一次会话中提供给 AI 工具继续排查。

---

## 项目核心数据流

供 AI 工具理解系统全貌：

```
                定时触发（每60秒）
                    │
                    ▼
    ┌─ sources 表 ──▶ 找到到期站点 ──▶ 并发抓取（最多5个）
    │                                    │
    │                                    ├── RSS 站点 → feedparser 解析
    │                                    └── HTTP 站点 → httpx 抓取列表页
    │                                                        │
    │                                           提取文章链接列表
    │                                                │
    │                                    ┌───────────┘
    │                                    ▼
    │                              对每个文章URL：
    │                              ┌─ L1: URL哈希 ─ 重复? → 跳过
    │                              │
    │                              ├─ 抓取文章页面
    │                              │
    │                              ├─ Tier 1/2/3 内容提取
    │                              │
    │                              ├─ L2: SimHash 指纹 ─ 重复? → 标记
    │                              │
    │                              ├─ L3: 实体+时间 ─ 重复? → 关联事件
    │                              │
    │                              ├─ L4: 向量相似度 ─ 重复? → 跨语种关联
    │                              │
    │                              └─ 入库 articles + 更新 event_clusters
    │
    └─ 更新 source: next_crawl_at, 统计, 健康状态
```

