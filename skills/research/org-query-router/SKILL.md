---
name: org-query-router
description: 离线组织库查询总路由：根据问题类型选择 basic / named / multiturn。触发词：组织查询、涉华智库、美国智库、军工企业、非政府组织、台在美团体、FAPA、业务标签、二级类型、org-query-router、org-relation-query。
version: 0.1.0
author: hermes-xw
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [organization, router, think-tank, biz-tags]
    related_skills:
      - org-query-basic
      - org-query-named
      - org-query-multiturn
      - org-query-common
      - person-query-router
---

# 组织查询路由（薄入口）

面向离线组织库的自然语言组织筛选。**先判定类型，再按对应专项 skill 执行**；共用约定见 `org-query-common` → `references/common.md`。

## 类型 → Skill

| 问题类型 | 选用 skill | 典型说法 |
|----------|------------|----------|
| 群体发现 / 条件筛选 | `org-query-basic` | 美国涉华智库；军工+半导体；台在美团体 |
| 具名组织 | `org-query-named` | Brookings；FAPA；Lockheed Martin |
| 多轮指代 / 分页攒池 | `org-query-multiturn` | 其中再筛；这些组织；继续翻页 |

## 路由规则

1. **宽采样池语义（先于类型分流）**  
   上轮若为宽采样（`is_sample=true` / `has_more=true` / 命中远大于本批），且本轮含「其中 / 这些 / 上轮结果 / 再筛选」：  
   - **默认**：要命中集再筛 → 进 `org-query-multiturn`，禁止只拿展示页当下结论。  
   - **例外**：用户明确只要「你刚列出的这 N 个」→ 可对本批 `include_ids`，交付须标明样本范围。  
2. **含具体组织专名/缩写（Brookings、FAPA、某公司全名）为主意图** → `org-query-named`。  
3. **含「其中/这些/再筛选/继续」且承接上轮** → `org-query-multiturn`。  
4. **其余单轮群体筛选** → `org-query-basic`。  
5. 复合问题按**主意图**选一个专项；同轮内可衔接另一专项规则。

## 一律先说明的边界

- 无组织—组织关系边；无事件库（听证/报告时间轴）；不能给完备全量名单。  
- 组织→人员：锁定正式名后用人员库 `search_by_company`。  
- 细节与工具参数：读 `org-query-common/references/common.md`。

## 人员库

涉及人员筛选/涉华人员时，可衔接 `person-query-router`。
