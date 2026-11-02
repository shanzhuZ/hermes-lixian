---
name: person-query-public-figure
description: 人员库公众人物/民选政客查询：禁止用 senator 等词群体捞人；外部名单或联网候选后 lookup 核验。触发词：政客、参议员、议员、国会议员、明星、公众人物、民选官员、person-query-public-figure。
version: 0.1.0
author: hermes-lixian
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [identity, personnel, politician, public-figure]
    related_skills:
      - person-query-router
      - person-query-common
      - person-query-basic
      - person-query-multiturn
---

# 公众人物 / 民选政客

共用约定：`person-query-common/references/common.md`。

## 为什么单独一类

领英库对**民选官员/明星**覆盖极差。用 `title_keywords=senator` 会命中学生会 senator、论坛头衔等，**不能当民选政客结果交付**。

## When to Use

- 涉华/在华经历的美国政客、议员、参议员  
- 明星、知名公众人物是否在库、是否有在华履历  

## 禁止

- 禁止把 `senator` / `representative` / `congressman` / `member of congress` 等作为**唯一**群体检索条件并宣称找到政客名单  
- 禁止在空结果或噪声结果上硬编「美国参议员列表」

## 标准路径

1. **生成候选姓名**（用户提供 / 外部知识 / 联网搜索）  
2. 对每个姓名：`lookup_by_name`（加 `country`/`company`/`job_title` 收窄）或 `lookup_by_linkedin`  
3. 若需涉华证据：对命中的 `unique_id` 看 education/experience，或再 `get_by_unique_id`  
4. 交付时逐人写：是否在库、职位/机构是否像本人、涉华证据；同名异人单独标存疑  

## 可诚实降级的说法

- **已验证有效的降级查询**（2026-09 实测）：`biz_tag=涉华` + `location_country=united states` + `strict=true` + `title_keywords=["congress","congressional","legislative","diplomat","embassy","government affairs"]` → 命中 308，几乎全是国会山幕僚（legislative aide/correspondent/director/counsel）、州议会、职业外交官、政府事务，信噪比高。用这组「机构/职能词」而非 `senator`/`representative` 等「官衔词」。  \n- **反例证据**：同口径把 title 换成 `["senator"]` → 仅 24 命中，主体是学生会 senator、班级 senator、虚标头衔（如 "senator, representing the United States" @ 某投资论坛），确认官衔词群体检索失败。  \n- 库内更易出现：国会助理、外交、学生、同名路人  
- 可改为查「政界/外交/国会相关从业者」圈层，并声明**不是民选官员完备检索**  
- 群体 `search_persons` 若全是噪声 → 直接判策略失败，改走姓名核验

## 与多轮池语义

「上轮结果里再找政客」先按 `person-query-multiturn` / router 的**宽采样池语义**处理（不得把抽样页当全集）。  
本 skill 额外限制：即便已攒池，仍**禁止**用 senator 等词硬筛冒充民选名单；应姓名候选 → lookup 核验。可降级为政界从业者圈层并声明非民选完备检索。

## 示例

| 用户 | 做法 |
|------|------|
| 涉华的美国参议员 | 说明无法群体枚举 → 要名单或联网补候选 → `lookup_by_name` |
| XX 议员有没有在华学历 | `lookup_by_name` → 核 education_brief |
| 上轮宽采样后再找政客 | 先澄清池范围（攒池/全库/仅本批）；勿对抽样页用 senator 词硬筛；有姓名再核验 |
