---
name: person-relation-tag-query
description: 【兼容入口】人员库查询已拆分为 person-query-router 及专项 skill。触发词仍可用：涉华人员、涉台人员、涉港人员、人员关系查询、业务标签查询、person-relation-tag-query。请按 router 选型执行。
version: 0.4.0
author: hermes-lixian
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [identity, personnel, china-related, legacy]
    related_skills:
      - person-query-router
      - person-query-basic
      - person-query-exclude-or
      - person-query-multiturn
      - person-query-public-figure
      - person-query-common
      - org-relation-query
---

# 人员关系与业务标签查询（兼容入口）

本 skill 已拆分为：

| Skill | 职责 |
|-------|------|
| `person-query-router` | 薄路由：按问题类型选型 |
| `person-query-basic` | 基础筛选与 AND |
| `person-query-exclude-or` | NOT / OR / 条件替换 |
| `person-query-multiturn` | 多轮指代与分页攒池 |
| `person-query-public-figure` | 政客/名人（禁止 title 群体捞人） |
| `person-query-common` | 共用参数与输出约定 |

**执行时：加载并遵循 `person-query-router`，再进入对应专项；共用约定读 `person-query-common/references/common.md`。**

能力差距说明仍见同目录 `REQUIREMENT_GAP.md`。
