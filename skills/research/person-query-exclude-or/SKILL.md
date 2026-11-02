---
name: person-query-exclude-or
description: 人员库逻辑条件：NOT 排除、OR 满足任一、条件替换（不要A改看B）。触发词：排除、不要在华教育、不要退休、满足任一、或者、不要政客改高管、condition_logic、person-query-exclude-or。
version: 0.1.0
author: hermes-lixian
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [identity, personnel, boolean, exclude]
    related_skills:
      - person-query-router
      - person-query-common
      - person-query-basic
      - person-query-multiturn
---

# 人员排除与 OR / 条件替换

共用约定：`person-query-common/references/common.md`。

## When to Use

- NOT：不要在华教育、不要在华工作、不要退休  
- OR：在华工作**或**在华教育等「满足任一」  
- 替换：不要政客，改看企业高管（**换条件，不是 AND 叠加**）  

## NOT

| 意图 | 做法 |
|------|------|
| 涉华 AND NOT 在华教育 | `biz_tag` + 国家 + `exclude_edu_country=china` |
| 有在华教育 AND NOT 在华工作 | `edu_country=china` + `exclude_work_country=china` |
| NOT 退休 | `exclude_retired=true` |
| 任意 A AND NOT B | 正向查 B 得 id → `exclude_ids`；或池内差集 |
| 弱 `exclude_*_keywords` | 仅辅助，不可靠 |

注意：`work_in_target_retired_suspect` 勿当硬在华履历。

## OR

- `condition_logic=or`：业务标签 / 工作 / 教育 / 公司学校 / 行业职位 **满足任一**  
- `location_country` 与 `include_ids` **始终 AND**  
- 例：在华工作或在华教育且现居美国 → `work_country=china, edu_country=china, condition_logic=or, location_country=united states`  
- 仅「在华工作或教育」也可用 `biz_tag=涉华`（内部已是工作∨教育）

## 条件替换（互斥调整）

| 用户说法 | 正确 | 错误 |
|----------|------|------|
| 不要政客，看看高管 | 去掉政客相关 `title_keywords`，改为 ceo/director 等 | 政客词 AND 高管词叠在一起 |
| 不要美国人，改看英国 | 替换 `location_country`，不是美国 AND 英国 | |

若用户指代「其中这些人」再排除 → 结合 `person-query-multiturn` 的 `include_ids` / `exclude_ids`。
