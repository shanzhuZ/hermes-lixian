---
name: person-query-router
description: 离线人员库查询总路由：根据问题类型选择 basic / exclude-or / multiturn / public-figure。触发词：人员查询、涉华人员、涉台人员、涉港人员、人员关系查询、业务标签查询、person-query-router、person-relation-tag-query。
version: 0.1.0
author: hermes-lixian
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [identity, personnel, router, china-related]
    related_skills:
      - person-query-basic
      - person-query-exclude-or
      - person-query-multiturn
      - person-query-public-figure
      - person-query-common
      - org-relation-query
---

# 人员查询路由（薄入口）

面向离线领英身份库的自然语言人员筛选。**先判定类型，再按对应专项 skill 执行**；共用约定见 `person-query-common` → `references/common.md`。

## 类型 → Skill

| 问题类型 | 选用 skill | 典型说法 |
|----------|------------|----------|
| 基础筛选 / AND 组合 | `person-query-basic` | 涉华人员；在华教育；高通+在华学历；现居美国 |
| NOT / OR / 条件替换 | `person-query-exclude-or` | 不要在华教育；满足任一；不要政客改高管 |
| 多轮指代 / 分页攒池 | `person-query-multiturn` | 其中再筛；这些人；继续排除；翻页多取一些 |
| 政客 / 名人 / 民选官员 | `person-query-public-figure` | 参议员；议员；明星；某政客是否涉华 |

## 路由规则

1. **宽采样池语义（先于类型分流）**  
   上轮若为宽采样（`is_sample=true` / `has_more=true` / 命中远大于本批），且本轮含「其中 / 这些人 / 上轮结果 / 再筛选」：  
   - **默认**：用户要的是「整次查询命中集」里的再筛 → 进 `person-query-multiturn`，**禁止**只拿上轮展示的那一页（如 20 条）当下结论；须分页攒池或合并条件全库重查。  
   - **例外**：用户明确只要「你刚列出的这 N 人」→ 可对这 N 人 `include_ids`，交付须写清「仅本批样本，非全量命中」。  
   - 与 X 是什么无关（公司、行业、职位、圈层等同一套池语义）。  
2. **含民选政客/明星/知名公众人物** → 优先 `person-query-public-figure`（即使也带涉华或「其中」）；池语义仍按第 1 条，另叠加该类「不可群体枚举」限制。  
3. **含「其中/这些人/再筛选/继续」且承接上轮名单** → `person-query-multiturn`（先过第 1 条）。  
4. **含排除、满足任一、不要 A 改看 B** → `person-query-exclude-or`。  
5. **其余单轮筛选** → `person-query-basic`。  
6. 复合问题：按**主意图**选一个专项；需要时在同轮内衔接另一专项的规则（例如 basic 出池后转 multiturn）。

## 一律先说明的边界

- 无访华记录；无共同经历工具；无多跳关联；不能给全量涉华名单。  
- 细节与工具参数：读 `person-query-common/references/common.md`。

## 组织库

涉及组织发现/标签筛选时，可衔接 `org-relation-query`（组织侧能力以该 skill 为准）。
