---
name: org-relation-query
description: 离线组织库自然语言查询（兼容入口）。请优先按类型使用 org-query-router / basic / named / multiturn。触发词：组织查询、涉华智库、美国智库、军工企业、非政府组织、台在美团体、FAPA、业务标签、二级类型、org-relation-query。
version: 0.3.0
author: hermes-xw
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [organization, osint, think-tank, multi-turn, elasticsearch, biz-tags]
    related_skills:
      - org-query-router
      - org-query-basic
      - org-query-named
      - org-query-multiturn
      - org-query-common
      - person-query-router
---

# 组织智能查询（兼容入口 → V1.2）

本文件为**兼容壳**：执行时按 `org-query-router` 分流。

| 类型 | Skill |
|------|-------|
| 路由 | `org-query-router` |
| 群体筛选 | `org-query-basic` |
| 具名消歧 | `org-query-named` |
| 多轮/分页 | `org-query-multiturn` |
| 共用约定 | `org-query-common/references/common.md` |

## 快速要点

- 标签以 `llm_deepseek` 为主；`biz_tag=涉华` **自动展开** `涉华-*`  
- 翻页：`search_after` / `next_search_after`；`include_ids` ≤ 500  
- 画像字段：L1 / L2 / biz_tags / tag_confidence / evidence_brief  
- **无**组织关系边、**无**事件库；组织→人员用 identity `search_by_company`

不要在本壳内重复发明参数；一律以 `org-query-common/references/common.md` 为准。
