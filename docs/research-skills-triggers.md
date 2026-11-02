# 四个 Research Skill：触发词与提问示例

单聊时建议：`HERMES_HOME=D:\hermes-lixian`，再用 `.\chat.ps1 chat`。  
提问时尽量带上**触发词 + 具体对象**（名称 / 账号 / 事件 / 法案编号）。

---

## 1. 组织画像 · `org-portrait`

| 项 | 内容 |
|----|------|
| **何时用** | 要某 NGO / 智库 / 公司等机构的背景与社媒概览 |
| **触发词** | 获取组织画像、组织画像、机构画像、org-portrait |
| **建议提问** | `获取组织画像，自由之家` |
| | `组织画像：Freedom House，要官网背景与 Twitter/YouTube 发文概览` |

---

## 2. 社交账号画像 · `account-portrait`

| 项 | 内容 |
|----|------|
| **何时用** | 深挖**单个** Twitter/X 或 YouTube 账号（主页 + 近期发文；跨平台只列疑似关联） |
| **触发词** | 社交账号画像、账号画像、account-portrait、账号主页 |
| **建议提问** | `社交账号画像，Twitter @freedomhouse` |
| | `账号画像：YouTube 频道 Freedom House` |
| | `account-portrait，平台 twitter，账号 freedomhouse` |

---

## 3. 热点事件传播影响 · `event-spread-impact`

| 项 | 内容 |
|----|------|
| **何时用** | 某热点事件的时间线、传播主体、影响范围（不是单个账号/组织画像） |
| **触发词** | 热点事件传播、传播影响、事件传播、event-spread-impact、舆情时间线 |
| **建议提问** | `热点事件传播影响：<事件一句话>` |
| | `事件传播分析，关键词：……，时间大约在 ……，要时间线和主要传播账号` |
| | `event-spread-impact，分析「……」在 Twitter/YouTube 上的传播与影响` |

---

## 4. 法案研判 · `bill-impact-analysis`

| 项 | 内容 |
|----|------|
| **何时用** | 定位法案 → 内容与状态 → 相关发言 → 涉华加重观点 → 影响评估（已取代 `bill-social-stance`） |
| **触发词** | 法案研判、法案分析、法案发言、H.R./S.、bill-impact-analysis、bill-social-stance |
| **建议提问** | `研判 H.R.9028 中华人民共和国经纪商和投资顾问暂停法案` |
| | `分析某某法案内容、相关发言和影响，涉华要重点写` |
| | `法案发言 H.R.8365`（旧说法，仍走本 Skill） |

---

## 5. 人员库查询（已拆分）

| Skill | 何时用 | 触发词示例 |
|-------|--------|------------|
| `person-query-router` | 总入口 / 不确定类型 | 人员查询、涉华人员、person-query-router |
| `person-query-basic` | 单轮筛选、AND | 在华教育、高通、现居美国 |
| `person-query-exclude-or` | NOT / OR / 改条件 | 不要在华教育、满足任一、不要政客改高管 |
| `person-query-multiturn` | 其中再筛、分页攒池 | 其中、这些人、再筛选 |
| `person-query-public-figure` | 政客/名人 | 参议员、议员、明星 |
| `person-query-common` | 查参数与输出约定 | （一般不单独触发） |
| `person-relation-tag-query` | 旧名兼容 → 走 router | person-relation-tag-query |

---

## 怎么选

| 你想分析的对象 | 用哪个 |
|----------------|--------|
| 一个机构 / 组织 | `org-portrait` 或 `org-relation-query` |
| 离线人员库筛选 | `person-query-router`（再进专项） |
| 一个社交账号 | `account-portrait` |
| 一件热点事怎么传开 | `event-spread-impact` |
| 一部法案本身 + 发言 + 影响 | `bill-impact-analysis` |

---

Java 流式问答网关见：[`clients/lixian-chat/README.md`](../clients/lixian-chat/README.md)（sessionId/taskId + SSE；本阶段内存态，不落库）。
