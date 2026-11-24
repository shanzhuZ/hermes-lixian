# 人员查询共用约定（V1.1）

各 `person-query-*` skill 共用。专项 skill 只写本类策略；工具参数、证据与输出以本文为准。

## 数据与工具

- 索引：`dw_identity_info_lk_country_wise_new_all`（`identity-mcp`）
- 主工具：`search_persons`（Hermes 名可能带 `mcp_identity_mcp_` / `mcp__identity_mcp__` 前缀，以 tool_search 为准）
- 精确：`lookup_by_name` / `lookup_by_linkedin` / `get_by_unique_id`
- 组织衔接（可选）：`org-relation-query`、`search_by_company`
- **不做入库打标**；涉华/台/港仅查询时推导

## V1 范围

**可做：** 经历/现居/机构关键词；涉华台港推导；AND/OR；NOT；分页攒池 + `include_ids` 二次筛选。

**不可做（须告知用户）：** 曾访问；全量涉华名单；民选政客/明星完备群体检索；共同经历交集；人→机构→人多跳。

## search_persons 参数摘要

| 参数 | 含义 |
|------|------|
| `biz_tag` | 涉华 / 涉台 / 涉港（或英文别名） |
| `work_country` / `edu_country` | 工作/求学国家，如 `china`、`hong kong`、`taiwan` |
| `location_country` | **仅现居**；与 `include_ids` 在 `condition_logic=or` 时仍始终 AND |
| `company_keyword` / `school_keyword` | 公司或学校名（模型现场填写，**无 MCP 内置词表**） |
| `industry_keywords` / `title_keywords` | 口语→英文词；行业默认只打当前 `industry` |
| `exclude_edu_country` / `exclude_work_country` | 硬排除该国教育/工作 |
| `exclude_retired` | 排除 title 含 retired |
| `include_ids` / `exclude_ids` | 白/黑名单，**≤500** |
| `condition_logic` | `and`（默认）/ `or`（业务·经历·机构·行业·职位满足任一） |
| `search_after` | 上一页 `next_search_after` |
| `strict` | 关弱信号；仅 biz_tag 过宽会被拒绝 |
| `size` | 由模型按需填写，**最大 1000**（默认 20；过大可能触发工具输出截断） |

## 证据与交付

- `edu_in_target` / `work_in_target` → 可进「符合」
- `work_in_target_retired_suspect` → 存疑（退休段 country 常伪填）
- `is_sample=true` → 非全量；有硬证据仍须列出本批符合项
- `has_more` / `next_search_after` → 翻页攒池
- 交付前核对 `education_brief` / `experience_brief` / `industry`
- 上轮宽采样后的「其中再筛」：默认攒池或全库重查，禁止把展示页当命中全集（与再筛条件类型无关）；仅当用户明确「就这 N 人」才可对本批 `include_ids`，并标明样本范围

**输出格式（最低要求）：**

- 每个大点用加粗序号标题开头，如 `**一、符合人员**`、`**二、存疑/排除**`
- 有 3 条及以上名单时用 Markdown 表格，表头须包含「姓名」列，其余列按内容选取，不必固定
- 没有名单的回答不要硬套表格，用加粗序号标题 + 段落或列表即可
- 范围、是否采样、条数、是否分页合并、下一步仍须交代，均用白话写（可放在最后一个大点里）

**面向用户的文字（硬约束）：** 回答是给甲方、业务人员看的，不是给开发看的。
- 禁止出现任何接口参数名、字段名、工具名或代码写法，包括但不限于 `edu_country`、`work_country`、`location_country`、`biz_tag`、`edu_in_target`、`work_in_target`、`is_sample`、`has_more`、`search_after`、`next_search_after`、`include_ids`、`unique_id`、`strict`、`condition_logic`、`industry_keywords`、`title_keywords`；也不要写 `字段=值` 形式的条件串。
- 筛选口径用白话，例如「有台湾或香港求学经历」；证据用「教育经历中可见对应地区院校」；采样用「本批为抽样样本，非全量名单」。
- 提示下一步收窄时只说业务含义（现居地、行业、院校、公司等），禁止写游标、参数名或「按 next_search_after 翻页」。
- 上述参数名仅供内部调用，不得写入给用户的文字。

**宽查询呈现（硬约束）：**
- 用户已给出的条件按原样检索，**禁止静默追加**国家/现居/行业等用户未提的限制。
- 估计命中很大（如过千、过万）时：先写总览（口径白话 + 约多少人 + 本批非全量）；表格每方向或合计不超过约 15 行；然后用白话请用户选收窄维度，不要先堆满 40 行再说明。
- 抽样展示时，尽量让现居地/背景有一定多样性，避免整表都是「本地求学且现居本地」而观感像未筛选；若本批确实偏本地，在说明里点明并给出可叠加的现居/行业选项。

禁止：有硬证据却整篇只写「采样噪声不可交付」。  
禁止：宽采样未攒池时，对「其中再筛」给出「全无/没有」类命中集结论。

## 关键词约定

- 行业/学校/公司由模型按用户说法生成，一次 2～4 个高信号词  
- 「高科技」→ 自行展开为英文 industry 词，交付时仍核对 `industry` 字段  
- **高校任职**用 `company_keyword`（大学作雇主）；**在该校上学**用 `school_keyword` / `edu_country`  
- 歧义词：避免裸 `senator` / `representative` / `member`

## 宽查询默认

- 仅说「涉华人员」等**极宽且无任何硬条件**时：先澄清要不要限定现居/行业；用户明确让你决定 → 内部可用 `biz_tag=涉华` + `location_country=united states` + `strict=true`，但交付须用白话写明「本次按涉华 + 现居美国的默认口径」。
- 用户已给出求学/工作/现居/院校/公司等任一具体条件（如「港台求学」「在华工作」）→ **只按已给条件查**，不要再默认叠加现居美国。
