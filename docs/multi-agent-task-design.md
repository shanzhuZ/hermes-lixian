# hermes-xw：深度规划入库 + 多 Agent 协同任务设计

> 状态：设计草案（v0.2 · 已对齐需求确认）  
> 目标：先规划、步骤入库、自动执行；顶层 Orchestrator **只调度不执行业务工具**；模块 Agent 为真·多 Profile / 多进程。  
> 存储：首期用 Hermes 自带 DB（Kanban / SQLite），任务与业务结果分库；后续可迁 ES/MySQL 供 Java 服务读取。  
> 参考：NousResearch/hermes-agent（Kanban / plan / delegate_task）、tonbistudio/hermes-multi-agent-workflow。

---

## 0. 已确认的产品决策（需求基线）

| # | 决策 | 含义 |
|---|------|------|
| A1 | 工程向深度思考 | 步骤必须入库，可审计；**不是**只做聊天展示 |
| A2 | 显式触发 | 仅指定 Skill / 口令触发，**非**所有复杂问题默认开启 |
| A3 | 通用框架 | 首期用法案社交验证；后续可挂写报、采集等 Skill |
| A4 | 自动执行 | 规划入库后**无需人确认**，直接往下跑 |
| B5 | 真多 Agent | 多 Profile / 多进程（对齐官方 Kanban），非单会话假分身 |
| B6 | 顶层只调度 | Orchestrator **禁止**自己调 Twitter 等业务 MCP |
| B7 | 步骤名动态 | 按任务生成步骤标题与角色，**不写死** Twitter/YouTube/… 固定角色表 |
| C8 | 先 Hermes DB | 首期 Kanban/SQLite；后续可迁 ES 或 MySQL |
| C9 | 对外可读 | 除 Agent 调度外，**Java 等业务服务也要能读**任务进度 |
| C10 | 分库存 | 任务步骤库 ≠ 业务结果库（如 `xw_law_related_info`） |
| D11 | 聊天可见过程 | 聊天流式刷步骤状态即可；不做独立看板（首期） |
| D12 | 部分成功 | 部分步骤失败 /「暂无信息」仍出报告 |
| D13 | 续跑延后 | **首期不考虑**中断续跑 |
| E14 | Skill 改写成规则 | Skill 只描述约束与验收，**不描述执行顺序** |
| E15 | 优先官方能力 | 尽量用上游 Kanban / Profile / dispatcher，少自研调度内核 |
| E16 | P0 验收 | 单 Skill **串行**：规划入库 → 逐步执行 → 出报告 |

---

## 1. 背景与目标

### 1.1 现状

| 项 | 现状 |
|----|------|
| 运行时 | `HERMES_HOME=D:\hermes-lixian`，单 Agent 循环 + MCP |
| 能力载体 | Skill（如 `bill-social-stance`）把「规则 + 执行顺序」写在一起 |
| 痛点 | 长任务边想边做难审计；步骤不落库；顶层与检索耦合；难扩展到写报/采集 |

### 1.2 目标形态

```
用户：显式触发（Skill / 口令）
        │
        ▼
┌───────────────────┐
│  Orchestrator     │  只做：拆步、定依赖、选 Profile、写库、汇总
│  （顶层 Agent）    │  不做：业务检索 / 写报 / 采集工具调用
└─────────┬─────────┘
          │ 写入 Hermes Kanban DB（步骤持久化）
          │ 聊天展示规划清单 → 自动开始执行
          ▼
┌───────────────────┐
│  Task Store       │  Hermes 自带 DB（首期）
│  （Kanban SQLite） │  后续投影/迁移 → ES 或 MySQL（供 Java 读）
└─────────┬─────────┘
          │ dispatcher 按依赖拉起 Worker Profile（真多进程）
          ▼
┌─────────────────────────────┐
│  动态 Worker（按步骤生成）   │  每步一个 Profile / 一次 claim
│  名称与工具集随任务变化      │
└─────────────┬───────────────┘
              ▼
     业务结果写入独立索引/库（与任务库分离）
     聊天输出：过程状态 + 最终报告（允许部分成功）
```

### 1.3 硬原则

1. **先规划再执行**：步骤未入库不得开始业务执行。  
2. **Orchestrator 零业务工具**：只能 task/kanban 类工具 + 汇总话术。  
3. **Skill = 规则与验收**：执行顺序由 Orchestrator 动态规划。  
4. **任务库与结果库分离**。  
5. **显式触发 + 入库后自动跑**（无人审门）。  
6. **部分失败仍交付**可读报告；失败步骤在报告中标明。

---

## 2. 执行原语

| 维度 | A. `delegate_task` | B. Kanban Task Store（主路径） |
|------|--------------------|--------------------------------|
| 形态 | 同进程短 fork→join | 多 Profile：create → claim → complete |
| 持久化 | 无 | Hermes 自带 DB |
| 本项目 | Worker **内部**偶尔用 | **业务主路径**；Orchestrator 只走这条 |

首期不实现崩溃续跑；DB 仍写入，便于审计与日后给 Java 读，以及 P2 再做续跑。

---

## 3. 任务数据模型

### 3.1 存储策略

| 阶段 | 任务步骤 | 业务结果（发言/写报成品等） |
|------|----------|---------------------------|
| P0 | Hermes Kanban DB（`kanban.db`） | 独立索引，如 `xw_law_related_info` |
| 后续 | 同步或迁移到 ES / MySQL | 保持独立索引/表 |

**给 Java 读（C9）：** P0 可先提供只读导出（定期 JSON/API 读 SQLite 或 Kanban HTTP）；迁移 ES/MySQL 后 Java 直连业务库。任务进度与业务结果始终分索引。

### 3.2 任务字段（映射到 Kanban + metadata）

一步一行。步骤 **title / agent 指向动态生成**，不预设固定 role 枚举。

| 字段 | 说明 |
|------|------|
| `task_id` | 主键 |
| `run_id` | 一次用户触发的批次 |
| `parent_task_ids` | 依赖；全部 done 后才 ready |
| `title` | **动态**步骤名（模型生成，如「检索 X 上 H.R.8365 精确编号帖」） |
| `description` | 给 Worker 的完整指令（含规则 Skill 要点 + payload） |
| `assignee_profile` | 动态选定或临时 Profile |
| `skill_rules` | 引用的规则 Skill 名（如 `bill-social-stance`） |
| `status` | `planned` → `ready` → `running` → `done` / `failed` / `blocked` |
| `payload` | 闸门与业务参数（JSON） |
| `result_summary` / `result_refs` | 摘要与产出引用 |
| `error` | 失败原因（部分成功时写入报告） |
| `created_at` / `started_at` / `finished_at` | 时间戳 |

### 3.3 `payload` 示例（法案场景；其他 Skill 换字段）

```json
{
  "target_bill_no": "H.R.8365",
  "target_title_zh": "促进解决西藏与中国冲突法案",
  "target_title_en": "Promoting a Resolution to the Tibet-China Conflict Act",
  "target_congress": "117",
  "acceptance": "仅纳入原文含目标编号变体的发文；否则该步结果标暂无信息"
}
```

写报 / 采集等后续 Skill：换用各自闸门字段，框架不变。

### 3.4 事件（聊天过程用）

可选：`plan_created` / `step_started` / `step_completed` / `step_failed`。  
首期以聊天流式状态为主，不强制独立事件表。

---

## 4. 运行时行为（通用；法案仅为示例）

### 4.1 触发

仅当用户显式要求时进入本模式，例如：

- 「按 bill-social-stance 深度执行 …」
- 约定口令 / 开关（实现时定名，如 `/deep-plan`）
- 后续：「按写报 Skill 深度执行 …」

未触发则保持现有单 Agent 行为。

### 4.2 生命周期

1. Orchestrator 读取**规则 Skill**（无执行顺序章节，或忽略其中的顺序描述）。  
2. **动态**生成步骤列表（title、依赖、assignee_profile、description）。  
3. **整表写入** Kanban DB，得到 `run_id`。  
4. 向用户聊天输出规划清单。  
5. **立即自动执行**（串行 P0）：dispatcher / Orchestrator 按依赖 claim → 拉起 Worker → complete。  
6. 每步在聊天更新：`[进行中] …` / `[完成] …` / `[失败] …`。  
7. 全部结束（含部分失败）→ 汇总报告 + `run_id`；业务结果写入**结果库**。

### 4.3 示例步骤（动态生成示意，非固定模板）

某次法案任务可能生成：

| 序 | title（示例） | 依赖 |
|----|---------------|------|
| 0 | 锁定目标法案身份字段 | — |
| 1 | 在 X 上按编号变体检索并过滤 | 0 |
| 2 | 在 YouTube 上检索并过滤 | 0 |
| 3 | 经 Apify 查 IG/FB/TG | 0 |
| 4 | 校验原文链接并补全账号信息 | 1,2,3 |
| 5 | 汇总立场并写中文报告 | 4 |
| 6 | 写入业务结果索引 | 5 |

另一次写报任务会生成完全不同的 title/依赖；**框架不绑定上表**。

### 4.4 状态机

```
planned ──(依赖满足)──► ready ──(claim)──► running ──► done
                                              │
                                              └──► failed / blocked
```

任一步 `failed`/`blocked`：**不取消整单**；后续不依赖它的步骤可继续；最终报告标注缺失部分。

### 4.5 部分成功报告规则

- 有成功步骤产出 → 必须出报告。  
- 失败步骤：写明原因（如无 APIFY_TOKEN、零命中、工具错误）。  
- 规则 Skill 要求「暂无信息」的，按规则写，禁止用相似目标充数。

---

## 5. Agent 职责

### 5.1 Orchestrator（顶层）

| 允许 | 禁止 |
|------|------|
| 读规则 Skill、生成步骤、写 Kanban | 调用 Twitter/YouTube/Apify/采集/写报等业务 MCP |
| 选/指定 Worker Profile、看任务状态 | 自己检索、自己写业务结果冒充 Worker |
| 汇总各步 `result_summary` 成用户报告 | 跳过入库直接执行 |

### 5.2 Worker（模块 Agent）

- 由 Kanban dispatcher 以**独立进程 + Profile**拉起（真多 Agent）。  
- 只领取自己的 `task_id`，按 `description` + 规则 Skill 执行。  
- 完成后 `kanban_complete`（或等价）写 summary / refs / error。  
- 内部可用 `delegate_task` 做短推理，但不得改写 `run` 级目标闸门。

### 5.3 不设固定角色枚举

不再把 `twitter` / `youtube` / `apify` / `report` 写成架构级死角色。  
实现上可预置若干 **可复用 Profile 模板**（如 `social-search`、`report-writer`），由 Orchestrator **按步动态选用并生成步骤名**。

---

## 6. 与官方 Hermes 的映射（优先官方）

| 需求 | 官方能力 | 用法 |
|------|----------|------|
| 步骤入库 + 多 Profile | Kanban + dispatcher | **主路径，首期直接用** |
| 编排方法论 | `kanban-orchestrator` Skill | Orchestrator 侧参考/裁剪 |
| 规则与验收 | 各业务 Skill（改写后） | 只保留 GATE / 输出格式 / 禁止项 |
| 规划文案（可选） | `plan` Skill → `.hermes/plans/` | 可给人看；**执行态以 Kanban 为准** |
| 短子问题 | `delegate_task` | 仅 Worker 内部 |

自研范围（尽量小）：触发口令、Orchestrator 行为契约、规则 Skill 改写、Kanban → Java 可读同步、聊天状态文案。

---

## 7. Orchestrator 行为契约

**触发：** 显式 Skill / 口令（名称实现时确定）。

**必须：**

1. 只加载规则 Skill + 用户问题，生成动态步骤（含依赖）。  
2. 全部 persist 到 Kanban 后再执行。  
3. 聊天先发规划清单，再自动逐步跑。  
4. 自身不调用业务 MCP。  
5. 结束时输出报告（允许部分成功）并给出 `run_id`。

**禁止：**

- 未 persist 就执行  
- 顶层做检索/写报/采集  
- 用相似目标绕过规则 Skill 的 GATE  

---

## 8. Skill 改写规范（E14）

业务 Skill（含 `bill-social-stance`）应逐步改成：

| 保留 | 删除或标为「非执行契约」 |
|------|-------------------------|
| 何时触发、输入字段 | 「步骤 1/2/3」固定流水线 |
| 身份 GATE / 验收 / 禁止项 | 「先搜 A 再搜 B」的强制顺序 |
| 输出必须含哪些块（账号/发文/链接/立场等） | 绑定特定 MCP 调用顺序的长教程（可改为 reference 附录） |

执行顺序、并行、选哪个 Profile → **一律交给 Orchestrator 动态规划**。

---

## 9. 实施分期

### P0（验收 = E16）

- [ ] 启用官方 Kanban + 至少一个 Orchestrator Profile（无业务 MCP）+ 至少一个 Worker Profile  
- [ ] 显式触发入口（口令或 Skill 包装）  
- [ ] 流程：**规划 → 入库 → 串行执行 → 聊天状态 → 报告**  
- [ ] 将 `bill-social-stance` 改为规则型（或新增 rules 版并行验证）  
- [ ] 业务结果仍写独立索引；任务只在 Kanban DB  
- [ ] **不做**：并行扇出、中断续跑、独立看板  

### P1

- [ ] 同 run 内无依赖步骤并行  
- [ ] Kanban 进度只读 API / 导出，供 Java 消费  
- [ ] 更多规则 Skill（写报、采集）挂接  

### P2

- [ ] 任务库迁移或双写 ES/MySQL  
- [ ] 中断续跑  
- [ ] 可选 Dashboard  

---

## 10. 验收标准（P0）

1. 显式触发后，**先**出现规划清单，且 Kanban DB 中有对应任务行。  
2. Orchestrator 工具调用记录中**无**业务检索类 MCP。  
3. 串行执行过程中聊天有步骤状态更新。  
4. 最终报告符合规则 Skill；部分步骤失败时仍有报告并标注失败步。  
5. 任务行与业务结果文档分属不同存储。  
6. **不测**中断续跑。

---

## 11. 风险与注意

| 风险 | 缓解 |
|------|------|
| 动态步骤质量不稳 | 规则 Skill 写清验收；Orchestrator prompt 约束最小步骤集 |
| 官方 Kanban 与 Java 读写 | P1 只读导出；避免 Java 直接抢写 claim |
| Skill 改写不彻底 | 旧版顺序章节加「忽略执行顺序，仅供参考」 |
| 顶层「顺手」调工具 | Profile toolset 白名单：仅 kanban_* |

---

## 12. 下一步

1. 盘点当前 `hermes-agent` 的 Kanban / Profile 是否可用并启用。  
2. 定触发口令与 Orchestrator Profile 配置。  
3. 改写 `bill-social-stance` 为规则型 + 跑通 P0 串行样例。  
4. （并行）仓库 `git push` 到 GitHub（需本机 PAT）。

---

## 附录 A：一次 run 的任务 JSON 示意

```json
{
  "run_id": "run_hr8365_20260807",
  "trigger": "deep-plan + bill-social-stance",
  "user_query": "检索 H.R.8365 社交发言与立场",
  "tasks": [
    {
      "task_id": "t0",
      "title": "锁定目标法案身份字段",
      "status": "planned",
      "parent_task_ids": [],
      "assignee_profile": "orchestrator",
      "skill_rules": "bill-social-stance",
      "payload": {
        "target_bill_no": "H.R.8365",
        "target_title_zh": "促进解决西藏与中国冲突法案"
      }
    },
    {
      "task_id": "t1",
      "title": "在 X 上按编号变体检索并过滤",
      "status": "planned",
      "parent_task_ids": ["t0"],
      "assignee_profile": "social-search",
      "skill_rules": "bill-social-stance"
    },
    {
      "task_id": "t2",
      "title": "汇总账号、发文与立场报告",
      "status": "planned",
      "parent_task_ids": ["t1"],
      "assignee_profile": "report-writer",
      "skill_rules": "bill-social-stance"
    }
  ]
}
```

## 附录 B：参考链接

- [hermes-agent Kanban](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/kanban.md)  
- [kanban-orchestrator SKILL](https://github.com/NousResearch/hermes-agent/blob/main/skills/devops/kanban-orchestrator/SKILL.md)  
- [plan SKILL](https://github.com/NousResearch/hermes-agent/blob/main/skills/software-development/plan/SKILL.md)  
- [tonbistudio/hermes-multi-agent-workflow](https://github.com/tonbistudio/hermes-multi-agent-workflow)  
- 规则 Skill（待改写）：`skills/research/bill-social-stance/SKILL.md`
