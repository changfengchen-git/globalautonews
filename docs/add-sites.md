# 添加站点指南

## 目录

1. [快速添加](#快速添加)
2. [站点文件格式](#站点文件格式)
3. [批量导入](#批量导入)
4. [手动添加（API）](#手动添加api)
5. [站点属性说明](#站点属性说明)
6. [国家代码参考](#国家代码参考)
7. [语言代码参考](#语言代码参考)

---

## 快速添加

### 方式 1: 编辑 sites 文件

1. 编辑 `sites/sites0415` 文件，添加新站点（每行一个）
2. 运行导入脚本：

```bash
cd /Users/apple/Desktop/globalautonews
DATABASE_URL="postgresql+asyncpg://gan:password@localhost:5432/globalautonews" \
  python3 scripts/import_sites.py sites/sites0415
```

### 方式 2: 通过 API

```bash
curl -X POST "http://localhost:8000/api/sources" \
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

### 方式 3: 通过前端

访问 http://localhost:80/candidates，在候选审批页面添加。

---

## 站点文件格式

文件位置：`sites/sites0415`

### 支持的格式

```
# 格式 1: 完整 URL（推荐）
https://www.example.com/news
http://example.com/auto

# 格式 2: 域名
example.com
news.example.com

# 注释以 # 开头
# 这是注释

# 空行会被忽略
```

### 示例

```
# 印度汽车新闻
https://www.carwale.com/hi/news/
https://www.autocarindia.com/
cardekho.com

# 日本汽车新闻
https://www.bestcarweb.jp/
carview.co.jp
kuruma-news.jp

# 德国汽车新闻
mobile.de
adac.de
motor-talk.de
```

### 站点分组（建议）

为了便于管理，建议按地区分组：

```
# ============== 印度 ==============
https://www.carwale.com/hi/news/
https://www.autocarindia.com/

# ============== 日本 ==============
https://www.bestcarweb.jp/
carview.co.jp

# ============== 德国 ==============
mobile.de
adac.de
```

---

## 批量导入

### 预览模式（不写入数据库）

```bash
DATABASE_URL="postgresql+asyncpg://gan:password@localhost:5432/globalautonews" \
  python3 scripts/import_sites.py sites/sites0415 --dry-run
```

### 实际导入

```bash
DATABASE_URL="postgresql+asyncpg://gan:password@localhost:5432/globalautonews" \
  python3 scripts/import_sites.py sites/sites0415
```

### 导入其他文件

```bash
DATABASE_URL="postgresql+asyncpg://gan:password@localhost:5432/globalautonews" \
  python3 scripts/import_sites.py sites/my-new-sites.txt
```

---

## 手动添加（API）

### 添加单个站点

```bash
curl -X POST "http://localhost:8000/api/sources" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Motor1",
    "domain": "motor1.com",
    "url": "https://www.motor1.com/",
    "country": "US",
    "language": "en",
    "region": "North America",
    "tier": 1,
    "rendering": "static",
    "priority": "medium"
  }'
```

### 批量添加（脚本）

```bash
#!/bin/bash
# add_sites.sh

SITES=(
  "example1.com|Example One|US|en"
  "example2.com|Example Two|CN|zh"
  "example3.com|Example Three|JP|ja"
)

for site in "${SITES[@]}"; do
  IFS='|' read -r domain name country language <<< "$site"
  
  curl -X POST "http://localhost:8000/api/sources" \
    -H "Content-Type: application/json" \
    -d "{
      \"name\": \"$name\",
      \"domain\": \"$domain\",
      \"url\": \"https://$domain\",
      \"country\": \"$country\",
      \"language\": \"$language\",
      \"priority\": \"medium\",
      \"tier\": 1
    }"
  
  echo "Added: $domain"
done
```

---

## 站点属性说明

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 站点名称（显示用） |
| `domain` | string | 是 | 域名（唯一标识） |
| `url` | string | 是 | 首页或列表页 URL |
| `country` | string | 是 | 国家代码（ISO 3166-1 alpha-2） |
| `language` | string | 是 | 语言代码（ISO 639-1） |
| `region` | string | 否 | 地区（Asia/Europe/North America 等） |
| `tier` | int | 否 | 提取器等级（1=通用, 2=适配器, 3=定制） |
| `rendering` | string | 否 | 渲染方式（static/dynamic） |
| `priority` | string | 否 | 优先级（high/medium/low） |
| `has_rss` | bool | 否 | 是否有 RSS feed |
| `rss_url` | string | 否 | RSS feed URL |
| `crawl_interval_minutes` | int | 否 | 抓取间隔（分钟，默认 240） |

### Tier 说明

- **Tier 1**: 使用通用提取器（trafilatura），适合大多数站点
- **Tier 2**: 使用 YAML 适配器，适合结构固定的站点
- **Tier 3**: 使用定制爬虫，适合复杂站点（需要登录、JS 渲染等）

### Rendering 说明

- **static**: 静态 HTML，使用 httpx 抓取
- **dynamic**: 动态 JS 渲染，使用 Playwright 抓取

---

## 国家代码参考

| 地区 | 国家代码 |
|------|----------|
| **亚洲** | CN(中国), JP(日本), KR(韩国), IN(印度), TH(泰国), VN(越南), ID(印尼), MY(马来西亚), SG(新加坡), PH(菲律宾), HK(香港), TW(台湾), PK(巴基斯坦), AE(阿联酋), SA(沙特) |
| **欧洲** | DE(德国), FR(法国), GB(英国), IT(意大利), ES(西班牙), NL(荷兰), SE(瑞典), NO(挪威), DK(丹麦), FI(芬兰), PL(波兰), RU(俄罗斯), CZ(捷克), AT(奥地利), CH(瑞士), BE(比利时), PT(葡萄牙), RO(罗马尼亚), HU(匈牙利), UA(乌克兰) |
| **北美** | US(美国), CA(加拿大), MX(墨西哥) |
| **南美** | BR(巴西), AR(阿根廷), CL(智利), CO(哥伦比亚) |
| **大洋洲** | AU(澳大利亚), NZ(新西兰) |
| **非洲/中东** | ZA(南非), NG(尼日利亚), KE(肯尼亚), IL(以色列), EG(埃及), TR(土耳其) |

---

## 语言代码参考

| 语言 | 代码 |
|------|------|
| 英语 | en |
| 中文 | zh |
| 日语 | ja |
| 韩语 | ko |
| 德语 | de |
| 法语 | fr |
| 西班牙语 | es |
| 葡萄牙语 | pt |
| 俄语 | ru |
| 意大利语 | it |
| 泰语 | th |
| 越南语 | vi |
| 印尼语 | id |
| 阿拉伯语 | ar |
| 印地语 | hi |

---

## 常见问题

### Q: 导入时提示 "已存在" 怎么办？

A: 站点已存在，不会重复导入。如需修改，请使用 API 的 PATCH 端点。

### Q: 如何批量更新站点状态？

A: 使用 API：
```bash
# 暂停所有错误率高的站点
curl -X POST "http://localhost:8000/api/sources/batch-update" \
  -H "Content-Type: application/json" \
  -d '{"status": "paused", "filter": {"consecutive_errors_gte": 10}}'
```

### Q: 如何删除站点？

A: 目前不支持删除，只能归档：
```bash
curl -X PATCH "http://localhost:8000/api/sources/{id}" \
  -H "Content-Type: application/json" \
  -d '{"status": "archived"}'
```

### Q: 站点抓取失败怎么办？

A: 在站点列表页面点击"重试"按钮，或使用 API：
```bash
curl -X POST "http://localhost:8000/api/sources/{id}/retry"
```

### Q: 如何升级到 Tier 2？

A: 如果站点使用通用提取器效果不好，可以升级到 Tier 2：
```bash
curl -X POST "http://localhost:8000/api/sources/{id}/upgrade-tier"
```

---

## 站点管理页面

访问 http://localhost:80/sources 查看所有站点及其状态。

功能：
- 按状态/国家/优先级筛选
- 搜索站点
- 查看抓取统计
- 执行操作（重试、暂停、恢复、升级）
