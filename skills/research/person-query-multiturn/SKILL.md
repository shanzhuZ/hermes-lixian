---
name: person-query-multiturn
description: 人员库多轮与分页：其中/这些人二次筛选、search_after 攒池、include_ids 收窄。触发词：其中、这些人、再筛选、继续、翻页、二次查询、include_ids、search_after、person-query-multiturn。
version: 0.1.0
author: hermes-lixian
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [identity, personnel, multi-turn, pagination]
    related_skills:
      - person-query-router
      - person-query-common
      - person-query-basic
      - person-query-exclude-or
      - person-query-public-figure
---

# 人员多轮与分页攒池

共用约定：`person-query-common/references/common.md`。  
结果集只在**当前会话**记忆，不落库；`include_ids` ≤ 500。

## When to Use

- 「其中 / 这些人 / 他们 / 再筛选 / 继续 / 排除其中…」  
- 需要比单页 20 条更大的候选池再收窄  

## 指代 vs 全库（池语义）

| 用户意图 | 做法 |
|----------|------|
| 明确只要「你刚列出的这 N 人」 | `include_ids=本批 unique_id` + 新条件；交付标明「仅本批样本」 |
| 说「其中 / 上轮结果 / 这些人」且上轮是宽采样 | **默认**视为要命中集再筛：先分页攒池或合并条件全库重查，**禁止**只对展示页（如 20 条）下「没有/全无」类结论 |
| 要「全库意义上」再加条件（未指代名单） | **合并条件全库重查**，不要默认 include_ids |
| 上轮已攒够池（会话内已合并 ≤500） | 可用 `include_ids=合并池` 收窄 |

与再筛条件 X 的类型无关：公司、学校、行业、职位、圈层等同一套规则。  
新条件若本身不可靠群体检索（如民选官员），按对应专项 skill 处理，但仍不得假装「抽样页 = 全集」。

## 分页攒池

1. 同条件按需设 `size`（最大 1000），记下全部 `unique_id`  
2. `has_more=true` 时带上 `search_after=next_search_after` 继续拉  
3. 合并去重，够用即停（≤500）  
4. 再用 `include_ids=合并池` 收窄  

注意：单页应尽量凑满 `size`（MCP 已按 unique_id 去重补拉）；若 `returned` 仍小于 size 且 `has_more=false`，说明候选已尽。

宽采样上的「其中再筛」默认走本流程；未攒池前不得用本批 20 条代替命中集结论。

## 多轮三连（指代名单时）

1. R1：基础条件（可分页）→ 池 A（宽采样时 A 须为攒池或明示的本批样本）  
2. R2：`include_ids=A` + 收窄（如 `edu_country=china`）→ 池 B  
3. R3：`include_ids=B` + 再收窄（如行业词）  

每轮把 id **原样**带入；池外的人不会出现——终值是**当前池**下界，不是全库完备集。

## 与其它 skill

- 收窄条件里的 NOT/OR/替换 → 用 `person-query-exclude-or` 的参数写法  
- 首轮怎么查 → `person-query-basic`  
- 民选政客/明星等 → 池语义仍按上文；核验路径见 `person-query-public-figure`
