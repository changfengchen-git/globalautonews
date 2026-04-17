# T4.01 — 按需翻译服务

## 任务目标
实现文章的按需翻译功能，用户在前端点击翻译按钮时调用。

## 前置依赖
- T1.11（API）

## 需要创建的文件
- `api/services/translate.py`
- 修改 `api/routes/articles.py` 添加翻译端点

## 实现要求

1. **翻译 API**：
   ```
   POST /api/articles/{id}/translate
   Body: {"target_language": "zh"}  # 或 "en"
   ```

2. **翻译引擎**（按优先级选择）：
   - DeepL API（如果配置了 DEEPL_API_KEY）
   - Google Translate（免费，使用 googletrans 库作为备选）

3. **翻译内容**：
   - 翻译标题 → 存入 title_en 或 title_zh
   - 翻译正文前 2000 字 → 存入 content_en 或 content_zh
   - 已翻译的文章不重复翻译（检查对应字段是否为空）

4. **成本控制**：
   - 每篇文章只翻译一次（缓存到数据库）
   - 标题和正文分开翻译

## 验收标准

1. ✅ 翻译 API 调用后，数据库中对应字段有值
2. ✅ 重复调用不会产生额外 API 费用
3. ✅ 中文文章可以翻译成英文，日文文章可以翻译成中文
4. ✅ 无 API Key 时返回友好错误

---

# T4.02 — EventDetail 页面

## 任务目标
实现跨语种事件详情页面，展示同一事件在不同国家/语种的报道。

## 前置依赖
- T2.05（事件聚类）
- T2.06（Vue.js）
- T4.01（翻译服务）

## 需要创建的文件
- `web/src/views/EventDetail.vue`
- `api/routes/events.py`

## 实现要求

### API 端点
```
GET /api/events              — 事件列表（按 importance_score 排序）
GET /api/events/{id}         — 事件详情（含所有关联文章）
```

### 前端页面
1. **事件头部**：
   - 事件标题（中文+英文）
   - 覆盖统计：N 篇报道 | N 种语言 | N 个国家
   - 关键实体标签

2. **时间线视图**：
   - 按时间排列的文章卡片
   - 每张卡片显示：来源旗帜 + 原文标题 + 翻译标题
   - 可展开查看全文（原文/翻译切换）
   - 翻译按钮（点击触发 T4.01 的翻译 API）

3. **覆盖地图**（可选简化版）：
   - 用国家旗帜 emoji 列表代替地图
   - 显示哪些国家报道了此事件

## 验收标准

1. ✅ 事件列表按重要性排序
2. ✅ 事件详情展示所有关联文章
3. ✅ 翻译按钮可用
4. ✅ 原文/翻译切换正常

---

# T4.03 — Tier 2 适配器引擎 + 示例

## 任务目标
实现基于 YAML 配置的声明式适配器引擎，以及 2-3 个示例适配器。

## 前置依赖
- T1.08（通用提取器，作为 fallback）

## 需要创建的文件
- `crawler/extractors/adapter.py`
- `crawler/adapters/car1_hk.yaml`（示例）
- `crawler/adapters/vnexpress.yaml`（示例）

## 实现要求

### 适配器引擎 (AdapterExtractor)

```python
class AdapterExtractor:
    def __init__(self, adapters_dir: str = "/app/adapters"):
        """加载所有 YAML 适配器配置"""
        
    def has_adapter(self, domain: str) -> bool:
        """检查是否有该域名的适配器"""
        
    def extract_list(self, html: str, domain: str) -> list[str]:
        """从列表页提取文章 URL 列表"""
        
    def extract_article(self, html: str, url: str, domain: str) -> ExtractResult:
        """使用适配器提取文章内容"""
```

### YAML 适配器格式
```yaml
source_domain: car1.hk
list_page:
  article_selector: "article.post"    # CSS 选择器
  link_selector: "a.post-title"       # 文章链接选择器
  link_attribute: "href"              # 链接属性（默认 href）
  max_pages: 3                        # 最多翻几页
  next_page_selector: "a.next"        # 下一页按钮选择器
article_page:
  title_selector: "h1.entry-title"
  content_selector: "div.entry-content"
  date_selector: "time.published"
  date_format: "%Y-%m-%d"
  date_attribute: "datetime"          # 从属性取日期（而非文本）
  author_selector: "span.author-name"
  image_selector: "div.entry-content img:first-child"
  remove_selectors:                   # 从内容中移除的元素
    - "div.ad-container"
    - "div.related-posts"
    - "div.social-share"
    - "script"
    - "style"
```

### 在调度引擎中集成
修改 T1.10 的 crawl_source，增加 Tier 选择逻辑：
```python
if source.tier == 2 and adapter_extractor.has_adapter(source.domain):
    result = adapter_extractor.extract_article(html, url, source.domain)
elif source.tier == 1:
    result = generic_extractor.extract(html, url)
    if not result.success and adapter_extractor.has_adapter(source.domain):
        result = adapter_extractor.extract_article(html, url, source.domain)
```

## 验收标准

1. ✅ YAML 适配器可以正确加载和解析
2. ✅ 示例适配器可以正确提取对应站点的文章
3. ✅ 适配器引擎与调度引擎集成，tier=2 的站点使用适配器
4. ✅ 新增适配器只需添加 YAML 文件，不需要改代码

---

# T5.01 — 自动模板生成 (LLM → YAML)

## 任务目标
对通过审批的新源，使用 LLM 自动分析页面结构生成 YAML 适配器。

## 前置依赖
- T4.03（适配器引擎）
- T3.02（LLM 分析器）

## 实现要求

1. 当新源通过审批且 Tier 1 提取失败时触发
2. 抓取新源的文章列表页和 1 篇文章页的 HTML
3. 调用 LLM 分析 HTML 结构，生成 YAML 适配器配置（使用 T4.03 定义的格式）
4. 自动测试：用生成的适配器抓取 3 篇文章，检查质量
5. 质量合格 → 保存到 adapters/ 目录，source.tier 更新为 2
6. 质量不合格 → 标记为需要 Tier 3 定制

## 验收标准

1. ✅ LLM 生成的 YAML 格式正确
2. ✅ 生成的适配器可以正确提取至少 1 篇文章

---

# T5.02 — 发布时间模式学习

## 任务目标
分析每个站点的历史发布数据，学习其发布时间模式，在非活跃时段减少抓取。

## 前置依赖
- T2.02（自适应调频）

## 实现要求

1. **每日凌晨统计**：
   - 按 source_id 聚合最近 30 天的文章
   - 统计每小时的发布数量 → 更新 publish_hours
   - 统计每个工作日的发布数量 → 更新 publish_weekdays

2. **调频优化**：
   - 在发布高峰时段（前 3 个高峰时段）→ 缩短间隔
   - 在低谷时段（0 篇发布的时段）→ 跳过抓取
   - 周末发布量 < 工作日 30% 的站点 → 周末拉长间隔

## 验收标准

1. ✅ publish_hours 正确统计（格式 `[0,1,2,...,23]` 对应每小时文章数）
2. ✅ 高峰时段抓取更频繁
3. ✅ 低谷时段跳过抓取

---

# T5.03 — 性能调优 + 运维文档

## 任务目标
系统整体性能优化和运维文档编写。

## 前置依赖
- 全部前面的任务

## 实现要求

1. **性能调优**：
   - 数据库：分析慢查询，添加缺失索引
   - 向量索引：数据量达标后创建 IVFFlat 索引
   - 内存优化：分析 docker stats，调整各容器内存限制
   - 日志清理：配置定时清理 crawl_logs（调用 cleanup_old_crawl_logs()）

2. **运维文档**：`docs/operations.md`
   - 部署步骤（从零到运行）
   - 常用运维命令
   - 故障排查指南
   - 备份恢复流程
   - 如何添加新站点
   - 如何编写 Tier 2 适配器
   - 如何编写 Tier 3 定制爬虫

3. **定时任务清单**：
   ```
   每 60 秒：扫描待抓取站点
   每小时：外链收集
   每天 02:00：站点健康检查 + days_without_new 更新
   每天 03:00：发布时间模式学习
   每天 04:00：清理旧 crawl_logs
   每周日 03:00：paused 站点探活
   ```

## 验收标准

1. ✅ docker stats 显示内存使用在预算内
2. ✅ 运维文档完整，步骤可执行
3. ✅ 所有定时任务正常运行
