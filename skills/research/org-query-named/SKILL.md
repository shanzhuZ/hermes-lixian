---
name: org-query-named
description: 具名组织查询与消歧：按名称/缩写定位单组织画像，处理同名噪声与库内未收录。触发词：FAPA、Brookings、Lockheed、某组织是什么、lookup_org_by_name、org-query-named。
version: 0.1.0
author: hermes-lixian
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [organization, lookup, disambiguation]
    related_skills:
      - org-query-router
      - org-query-common
      - org-query-basic
      - person-query-router
---

# 具名组织查询

共用约定：`org-query-common/references/common.md`。

## When to Use

- 用户给出组织专名、缩写、品牌名（FAPA、Brookings、CSIS、Lockheed…）  
- 「某某组织是什么 / 有什么标签 / 在哪」  

不要用于：群体发现（→ basic）；「与某某有合作的组织」（关系边未入库，须说明）。

## 策略

1. 优先 `lookup_org_by_name(name=...)`；已知类型/国家时加上 `org_type` / `location_country`。  
2. MCP 会对短名加别名加分（如 FAPA→Formosan Association…），但**不会因完整名不在库而查空**。  
3. 若返回 `coverage_hint`：说明完整目标名可能**未收录**；勿把城市/报刊/同缩写协会当目标交付。  
4. 若返回 `disambiguation_hint`：对比 `org_types`、国家、`biz_tags`、`description` 选目标；必要时请用户确认。  
5. 命中后输出完整画像卡片（含 L1/L2/`biz_tags`/`tag_confidence`/`tag_reason`/`evidence_brief`）。  
6. 「该组织有哪些人」→ 用正式名调 identity `search_by_company`。  
7. 「与 FAPA 关联的组织」→ 说明 V1 无关系边；可改为群体筛选（如 `org_type=台在美团体, biz_tag=涉台`）作弱近似，并标明非关系查询。

## 示例

| 用户意图 | 调用 |
|----------|------|
| FAPA 是什么 | `lookup_org_by_name("FAPA")`；确认 Formosan Association… |
| Brookings 智库 | `lookup_org_by_name("Brookings", org_type="智库")`；若仅城市/报刊噪声且有 coverage_hint → 说明库内未收录 Institution |
| Lockheed | `lookup_org_by_name("Lockheed Martin")` 或 `name_keyword` + `org_type=军工` |
