---
name: person-query-common
description: 人员查询共用约定与参数说明（被其它 person-query-* 引用）。一般不单独触发；需要查阅工具参数、证据字段、输出格式、V1 边界时使用。触发词：person-query-common、人员查询共用约定。
version: 0.1.0
author: hermes-lixian
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [identity, personnel, reference]
    related_skills:
      - person-query-router
      - person-query-basic
      - person-query-exclude-or
      - person-query-multiturn
      - person-query-public-figure
---

# 人员查询共用约定

本 skill 提供**共用参考**，不负责独立答题流程。

1. 先读同目录 `references/common.md`（工具参数、证据、输出、V1 边界）。  
2. 实际检索请按问题类型切换到对应专项 skill（见 `person-query-router`）。  

不要把本 skill 当作唯一执行入口。
