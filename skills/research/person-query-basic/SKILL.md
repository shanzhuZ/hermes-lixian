---
name: person-query-basic
description: 人员库基础筛选与 AND 组合：涉华/台/港推导、在华港台教育或工作、现居、公司学校、行业职位。触发词：在华教育、在华工作、涉华人员、涉台、涉港、高通人员、现居美国、person-query-basic。
version: 0.1.0
author: hermes-lixian
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [identity, personnel, search, china-related]
    related_skills:
      - person-query-router
      - person-query-common
      - person-query-multiturn
      - person-query-exclude-or
      - person-query-public-figure
---

# 人员基础查询

单轮或「条件一次性说清」的筛选。参数/证据/输出见 `person-query-common/references/common.md`。

## When to Use

- 涉华 / 涉台 / 涉港（经历推导）  
- 在华、港、台的教育或工作经历  
- 现居国家 + 公司 / 学校 / 行业组合（AND）  

不要用于：其中再筛（→ multiturn）；NOT/OR/改条件（→ exclude-or）；政客名人（→ public-figure）。

## 策略

1. 宽查询（只说涉华）→ 先澄清；否则默认 `biz_tag=涉华` + `location_country=united states` + `strict=true`。  
2. 条件宜少而硬：`edu_country` / `work_country` / `location_country` / `company_keyword` / `school_keyword`。  
3. 关键词由模型现场生成；**高校任职**用 `company_keyword`，**上学**用 `school_keyword` 或 `edu_country`。  
4. 行业口语自行展开为 `industry_keywords`，交付时核对 `industry`，不符则剔除或存疑。  
5. 自检：有 `edu_in_target` / `work_in_target` 才进「符合」。  
6. 需要更大样本或「其中再筛」→ 转 `person-query-multiturn`。  
7. 交付若 `is_sample=true` / `has_more=true`：须说明本批非全集；引导下一步时写清——「其中再筛」默认要先攒池或全库重查，只有用户明确「就这 N 人」才可对本批 `include_ids`。

## 示例

| 用户意图 | 调用 |
|----------|------|
| 在华教育且现居美国 | `edu_country=china, location_country=united states, size=20, strict=true` |
| 在华教育且高通 | `edu_country=china, company_keyword=qualcomm` |
| 涉华+美国（默认口径） | `biz_tag=涉华, location_country=united states, strict=true` |
| 涉台+在台工作 | `biz_tag=涉台` 或 `work_country=taiwan`，按需加现居 |
