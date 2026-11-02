---
name: org-query-multiturn
description: 组织库多轮与分页：其中/这些组织二次筛选、search_after 攒池、include_ids 收窄。触发词：其中、这些组织、再筛选、继续、翻页、二次查询、include_ids、search_after、org-query-multiturn。
version: 0.1.0
author: hermes-xw
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [organization, multi-turn, pagination]
    related_skills:
      - org-query-router
      - org-query-common
      - org-query-basic
      - org-query-named
---

# 组织多轮与分页攒池

共用约定：`org-query-common/references/common.md`。  
结果集只在**当前会话**记忆；`include_ids` ≤ 500。

## When to Use

- 「其中 / 这些组织 / 他们 / 再筛选 / 继续 / 排除其中…」  
- 需要比单页 20 条更大的候选池再收窄  

## 指代 vs 全库（池语义）

| 用户意图 | 做法 |
|----------|------|
| 明确只要「你刚列出的这 N 个」 | `include_ids=本批 org_id` + 新条件；标明「仅本批样本」 |
| 「其中 / 上轮结果」且上轮宽采样 | **默认**分页攒池或合并条件全库重查，禁止只用展示页下「没有」类结论 |
| 全库意义上再加条件（未指代名单） | **合并条件全库重查** |
| 会话内已攒够池（≤500） | 可用 `include_ids=合并池` 收窄 |

## 分页攒池

1. 同条件 `size=20`，记下全部 `org_id`  
2. `has_more=true` 时带 `search_after=next_search_after` 继续拉  
3. 合并去重，够用即停（≤500）  
4. 再用 `include_ids=合并池` + 新条件收窄  

## 多轮三连（指代名单时）

1. R1：基础条件（可分页）→ 池 A  
2. R2：`include_ids=A` + 收窄（如 `biz_tag=涉台`）→ 池 B  
3. R3：`include_ids=B` + 再收窄  

每轮把 `org_id` **原样**带入；终值是当前池下界，不是全库完备集。

## 与其它 skill

- 首轮怎么查 → `org-query-basic`  
- 收窄到某具名组织核实 → `org-query-named`  
- 再查人员 → `person-query-router` / `search_by_company`
