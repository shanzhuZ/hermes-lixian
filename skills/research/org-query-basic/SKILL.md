---
name: org-query-basic
description: 组织库基础筛选与 AND 组合：一级/二级类型、业务标签（涉华展开）、国家地区、行业议题。触发词：美国涉华智库、军工企业、非政府组织、台在美团体、半导体、org-query-basic。
version: 0.1.0
author: hermes-lixian
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [organization, search, biz-tags, think-tank]
    related_skills:
      - org-query-router
      - org-query-common
      - org-query-multiturn
      - org-query-named
---

# 组织基础查询

单轮或「条件一次性说清」的群体发现。参数/证据/输出见 `org-query-common/references/common.md`。

## When to Use

- 美国涉华智库 / 军工 / 高校 / NGO / 台在美团体 / 基金会等  
- L1 + 国家 + `biz_tag`（推荐）；需要时加 L2 / 行业 / 成立年  

不要用于：具名单组织（→ named）；其中再筛（→ multiturn）；关系边/事件（说明未入库）。

## 策略

1. 不确定类型/标签时先 `list_org_types`。  
2. 硬条件优先：`org_type` + `location_country` + `biz_tag`（`涉华` 会自动展开 `涉华-*`）。  
3. 细分类可用 `biz_tag=涉华-科技` 等；多标签 AND 用 `biz_tags`。  
4. 议题优先 `biz_tag`；`topic` 仅作别名；补召回才 `topic_fallback_text=true`。  
5. `军事安全议题` 面很宽，必须叠加类型+国家。  
6. 需要更高精度可加 `min_tag_confidence=0.7`（会降召回）。  
7. `is_sample` / `has_more`：说明本批非全集；「其中再筛」转 `org-query-multiturn`。  
8. 交付核对 `org_types` / `biz_tags` / `evidence_brief` / `tag_confidence`。

## 示例

| 用户意图 | 调用 |
|----------|------|
| 美国涉华智库 | `org_type=智库, location_country=united states, biz_tag=涉华, size=20` |
| 美国安全类智库 | `org_type=智库, org_type_l2=安全智库, location_country=united states` |
| 台在美团体+涉台 | `org_type=台在美团体, biz_tag=涉台` |
| 军工再叠半导体 | `org_type=军工, location_country=united states, biz_tag=半导体/科技竞争` |
| 涉华+涉台 AND | `biz_tags=["涉华","涉台"]` + 类型/国家 |
| 高置信涉华智库 | 同上 + `min_tag_confidence=0.75` |
