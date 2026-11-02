---
name: china-sensitivity-ecommerce-audit
description: 跨境电商平台（TeePublic、Redbubble、Zazzle、Walmart、eBay、Etsy 等）商品与商家涉华及涉中国领导人因素深度审查与情感研判。对 TeePublic/Redbubble/Zazzle/Walmart 调用专属 MCP，对 eBay/Etsy 直接调用 Firecrawl 智能采集，通过文本流与多模态图片流（基于 image-analysis PPLX 视觉 MCP）双流审查，精准识别正/负面倾向，针对负面违规商品与商家输出详细报告与原因溯源。触发词：涉华商品审查, 电商敏感排查, 涉政商品审核, 涉华负面商品, 领导人画像审查, china-sensitivity-ecommerce-audit.
version: 1.3.0
author: hermes-xw
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ecommerce, audit, china-sensitivity, pplx, firecrawl, teepublic, redbubble, zazzle, walmart, ebay, etsy, 涉华审查, 涉政排查, 情感研判, 领导人审查]
    related_skills: [teepublic]
---

# 跨境电商涉华与领导人因素审查（China-Sensitivity E-Commerce Audit）

本 Skill 规范了对主流跨境电商平台（TeePublic、Redbubble、Zazzle、Walmart、eBay、Etsy 等）商品数据与商家信息进行**涉华因素**与**涉中国领导人因素**深度审查的标准作业流程。

---

## 一、 平台采集分工矩阵（核心策略）

针对不同平台的反爬机制，采取最优采集通道：

```
┌─────────────────────────┬────────────────────────────────────────────────────────┐
│ 平台                    │ 首选采集通道与机制                                     │
├─────────────────────────┼────────────────────────────────────────────────────────┤
│ TeePublic               │ 【原生 MCP】teepublic-mcp (curl_cffi 原生过盾 + 自动存图)│
│ Redbubble               │ 【原生 MCP】redbubble-mcp (curl_cffi 原生过盾 + 自动存图)│
│ Zazzle                  │ 【原生 MCP】zazzle-mcp (curl_cffi 原生过盾 + 自动存图)   │
│ Walmart (PerimeterX盾)  │ 【原生 MCP】walmart-mcp (常驻有头 UC 浏览器 + 自动存图)  │
│ Etsy (DataDome盾)       │ 【Firecrawl】firecrawl_scrape / extract 智能云采集     │
│ eBay (Akamai盾)         │ 【Firecrawl】firecrawl_scrape / extract 智能云采集     │
└─────────────────────────┴────────────────────────────────────────────────────────┘
```

---

## 二、 标准执行全流程

```
[电商数据采集]
  ├── TeePublic / Redbubble / Zazzle / Walmart ──> 专属本地 MCP (搜索 + 详情 + 店铺)
  └── eBay / Etsy ───────────────────────────────> Firecrawl (JSON Schema 结构化提取)
         │
         ▼
[双流合规审查]
  ├── 文本流：扫描标题、描述、标签、卖家 Bio
  └── 图片流：调用 image-analysis MCP (PPLX 多模态模型) 审查设计图/Mockup/头像
         │
         ▼
[倾向研判与输出]
  ├── 正面 (Positive) / 中性 (Neutral) ──> 归档统计
  └── 负面 (Negative) ───────────────────> 🚨 触发负面告警与证据链溯源报告
```

---

## 三、 数据采集执行规范

### 1. TeePublic（调用专属 MCP）
- 搜索：`search_teepublic(query=..., category="t-shirts", save_json=True, download_images=True, save_dir=...)`
- 详情：`get_teepublic_product_details(product_url_or_id=..., save_json=True, download_images=True)`
- 卖家：`get_teepublic_artist_info(artist_name_or_url=..., save_json=True, download_images=True)`
  *(注意：卖家查询必须使用商品详情返回的 `artist_slug`)*

### 2. Redbubble（调用专属 MCP）
- 搜索：`search_redbubble(query=..., save_json=True, download_images=True, save_dir=...)`
- 详情：`get_product_details(product_url_or_id=..., save_json=True, download_images=True)`
- 卖家：`get_artist_info(artist_name_or_url=..., save_json=True, download_images=True)`

### 3. Zazzle（调用专属 MCP）
- 搜索：`search_zazzle(query=..., page=1, save_json=True, download_images=True, save_dir=...)`
- 详情：`get_zazzle_product_details(product_url_or_id=..., save_json=True, download_images=True)`
- 卖家：`get_zazzle_store_info(store_name_or_url=..., save_json=True, download_images=True)`

采集要点：
- **关键词拼写坑**：Zazzle 搜索必须用空格分隔的全名（如 `xi jinping`），连写（`xijingping`）会返回 0 条；拼写错误（如 `xi jimping`）不会报错而是返回一堆无关模糊匹配（如生日邀请函），必须丢弃。涉领导人搜索先试空格全名，命中后再决定是否补变体（姓氏连写类关键词同理）。
- **大响应截断处理**：`get_zazzle_store_info` 响应可超 50KB（60 件商品列表），工具会把完整输出持久化到 cache 文件并在内联返回中截断。所有采集务必 `save_json=True`，截断时直接读本地 JSON 为准：`D:/hermes-lixian/mcp/data/zazzle/json/artist_{handle}_p1_*.json`（搜索 `search_*.json`、详情 `product_*.json` 同理），不要依赖内联响应。
- **价格语义**：搜索结果 `price` 是划线原价，商品详情页 `price` 才是折后实付价；`strike_through_info` 含原价/折后价/折扣率。对外报告用详情页价格并标注折扣；只有搜索层数据时用 `strike_through_info.priceAdjusted`。
- **店铺规模口径**：`total_products_on_page` 是当前页商品数（上限 60），不是店铺总库存；做店铺违规集中度统计需翻页累加。
- 搜索单页返回 60 条完整记录，且每条已直接携带 `store_handle` 与 `store_url`，**无需再从详情页反查即可直接进入卖家审查**，这是与 TeePublic 的关键差异。
- 卖家查询传 `store_handle`（如 `LambertaupIbQE`）或完整店铺 URL 均可；内部会优先请求商品最全的 `/store/{handle}/products` 子页。
- 详情页 `category` 为多级面包屑（如 `Clothing & Shoes > Men's Fashion > ... > Men's T-Shirts`），`features` 为卖点条目，`details` 含款式、颜色、尺寸、浏览量，这些均应纳入文本流扫描。
- 图片流优先使用 `local_images`（详情）与 `local_image`（搜索/店铺）本地路径；`images` 字段中的 `rlv.zcache.com` 直链需带 Referer 才能访问，MCP 下载时已自动处理并过滤 1KB 以下占位图。

### 4. Walmart（调用专属 MCP）
- 搜索：`search_walmart(query=..., page=1, save_json=True, download_images=True, save_dir=...)`
- 详情：`get_walmart_product_details(product_url_or_id=..., save_json=True, download_images=True)`
- 卖家：`get_walmart_seller_info(seller_id_or_url=..., save_json=True, download_images=True)`

采集要点：
- **卖家 ID 有两个，别用错**：详情返回的 `seller.seller_id` 是 32 位十六进制内部 ID，**不能**用来拼店铺地址；必须用 `seller.catalog_seller_id`（数字，如 `8351`）传给 `get_walmart_seller_info`，否则会拿到 "Uh-oh" 错误页。
- **卖家归属地是硬证据**：Walmart 公开第三方卖家的工商注册信息，`registered_name`（工商注册名，常与展示名不同）、`address.country`、`contact.country_code`、`address.city` 可直接判定卖家实际归属地，无需靠店铺名猜测。例如展示名 `Muujun`、注册名 `changshamujunmaoyiyouxiangongsi`、`country=CN`、`+86`、长沙地址。这是本平台相较其他平台的最大优势，涉华卖家溯源应优先采集此字段。
- 搜索单页返回 40–66 条，且每条已直接带出 `seller_name` 与 `seller_id`，**可先在搜索层筛出可疑卖家再进详情**。翻页依据返回的 `max_page`。
- **自营与第三方要区分**：`seller_name` 为 `Walmart.com` 的是平台自营，没有第三方店铺页，`get_walmart_seller_info` 会返回卖家节点缺失的错误，属预期行为，不必重试。
- **速度与并发**：本 MCP 靠常驻有头 UC 浏览器过 PerimeterX，首次调用约 35–45 秒（含浏览器启动），之后每页 13–20 秒；浏览器是单例资源，**工具调用必须串行，不要并发批量拉取**。服务实际跑在 WSL 的 Ubuntu 里、由 Xvfb 提供虚拟显示，不会占用桌面也不弹窗口。
- **图片路径可直接交给视觉模型**：虽然采集侧在 Linux，但返回的 `local_image` / `local_images` / `images_dir` 已回译为 `D:\...` 形式，Windows 上的 `image-analysis` MCP 可直接读取，无需转换。
- 偶发被 PerimeterX 拦截时 MCP 会自动长按重试并重建会话；若返回 `blocked by PerimeterX` 错误，间隔一两分钟再试，仍失败则改走 Firecrawl。
- 文本流扫描应覆盖 `name`、`long_description`、`highlights`、`specifications` 与 `category` 面包屑；卖家侧还需扫描 `about`（店铺简介）与 `registered_name`。
- 图片流优先用 `local_images`（详情）与 `local_image`（搜索/店铺）本地路径；`i5.walmartimages.com` 在线直链也可直接传给视觉模型。

### 5. Etsy（直接使用 Firecrawl 采集）
- **步骤 1（搜索列表）**：调用 `firecrawl_scrape`，传入 `https://www.etsy.com/search?q={query}`，`formats=["json"]`，提取商品列表（标题、URL、价格、卖家、评分），去重取前 N 个。
- **步骤 2（商品详情）**：调用 `firecrawl_extract` 或 `firecrawl_scrape`，批量提取前 N 个 listing URL 的完整描述、价格、全套高清图片（`i.etsystatic.com` 直链）及卖家 shop_url。
- **步骤 3（卖家店铺）**：抓取 `https://www.etsy.com/shop/{name}` 提取店铺介绍、头像、在售商品数与好评。
- 详细 Schema 与踩坑指引见 [references/etsy-firecrawl-fallback.md](references/etsy-firecrawl-fallback.md)。

### 6. eBay（直接使用 Firecrawl 采集）
- **步骤 1（搜索列表）**：调用 `firecrawl_scrape`，传入 `https://www.ebay.com/sch/i.html?_nkw={query}`，`formats=["json"]`，提取商品标题、价格、链接、卖家用户名、缩略图。
- **步骤 2（商品详情）**：批量提取商品详情、规格参数（Aspects）、详细描述及全套多角度大图（`i.ebayimg.com` 直链）。
- **步骤 3（卖家信息）**：抓取卖家主页 `https://www.ebay.com/usr/{username}` 提取信用评分、好评率。
- 详细 Schema 见 [references/ebay-firecrawl-recipe.md](references/ebay-firecrawl-recipe.md)。

---

## 四、 双流审查与倾向研判（调用 image-analysis MCP）

获取到商品数据与图片（本地图片路径或在线 URL 直链）后，直接调用 `image-analysis` MCP：

### 1. 文本与图片双流判定
调用 `audit_china_sensitivity` 工具：
```python
audit_china_sensitivity(
    image_path_or_url=item["main_image_url"],  # 支持本地路径或 etsystatic/ebayimg/teepublic/zcache/walmartimages 在线直链
    title=item["title"],
    description=item["description"],
    tags=item["tags"],
    artist_name=item["seller_name"],
)
```

### 2. 审查重点与倾向标准
- **涉领导人因素**：现任及历任领导人姓名、肖像、漫画形象、变脸恶搞、讽刺性代称隐喻（如维尼熊政治化组合）。
- **涉华政治与敏感因素**：分裂国家主权领土（涉台/涉港/涉疆/涉藏）、反华政治标语、篡改国旗国徽、地缘政治抹黑、种族歧视。
- **倾向划分**：
  - **正面 (Positive)**：优秀传统文化（龙、汉服、节气等）、友好民间交流。
  - **中性 (Neutral)**：客观商业/地理描述，无政治立场。
  - **负面 (Negative)**：**严重违规**，包含丑化/攻击领导人、分裂国家、抹黑攻击体制等 $\rightarrow$ **🚨 必须触发负面告警与证据输出**。

---

## 五、 负面审查结果输出模板

凡判定为 **【负面 (Negative)】** 的商品与商家，必须按照以下标准格式输出审查报告：

```markdown
# 跨境电商涉华/领导人负面违规商品排查报告

## 🚨 预警概览
- **排查平台**：[TeePublic / Redbubble / Zazzle / Walmart / eBay / Etsy]
- **检索关键词**：[例如：xijinping / china / ...]
- **排查商品总数**：N 个
- **命中负面违规数**：M 个商品 | K 个卖家

---

### 【违规商品 1】 [商品标题 / Title]
- **商品 ID**：`4350431965`
- **平台与链接**：[点击直达](https://www.etsy.com/listing/4350431965/...)
- **销售价格**：$91.38 USD
- **主要标签**：`sculpture`, `bust`, `art`, `Xi Jinping`
- **商品图片**：[查看高清图](https://i.etsystatic.com/...)

#### 👤 关联商家信息
- **商家名称**：Seller Name / Shop Name
- **店铺主页**：https://www.etsy.com/shop/LikeDimension
- **商家评分与评价**：5.0 星 (10 条评价)
- **工商注册主体与归属地**：注册名 / 国家 / 城市（Walmart 平台可直接取得，其余平台若无则标注「未公开」）
- **店铺违规集中度**：店铺共 N 件在售，涉政/敏感讽刺作品约 X 件

#### 🔍 判定原因与证据链
1. **文本流命中**：
   - 标题/描述中包含敏感实体与负面语境。
2. **图片流 pplx 视觉判定**：
   - 视觉模型识别结果：图像包含 [领导人丑化漫画/敏感政治符号/特定动物政治隐喻...]。
3. **综合定性**：
   - **风险等级**：🔴 高危 (High Risk) / 🟠 中危 (Medium Risk)
   - **违规类型**：[涉中国领导人恶意丑化 | 分裂主权与领土 | 涉华种族/政治攻击]
   - **详细判定说明**：[详细阐明其为何属于负面及其政治危害性]

---
```
