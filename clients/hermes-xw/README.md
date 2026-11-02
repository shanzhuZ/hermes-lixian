# hermes-xw Java 网关

从 hermes-xa 精简改造：对话接口区分 **sessionId（多轮历史）** 与 **taskId（单次 Skill 执行）**，并路由到四个 research Skill。

## 准备

1. MySQL 建库并执行 [`sql/schema.sql`](sql/schema.sql)（库名 `hermes-xw1`）；已有库可只跑 [`sql/alter_xw_ingest.sql`](sql/alter_xw_ingest.sql)
2. 改 [`src/main/resources/application.yml`](src/main/resources/application.yml)：
   - `spring.datasource.*`（默认已指向 `hermes-xw1`）
   - `hermes.base-url` / `hermes.api-key`（Hermes API Server，默认 `http://127.0.0.1:8642`）
3. Hermes：`.\scripts\init-hermes-runtime.ps1`（联接 `plugins/xw-ingest`），在 `.env` 配置 `XW_MYSQL_*`（与 Java 同一库），重启 API Server

## 启动

```powershell
cd D:\hermes-lixian\clients\hermes-xw
.\start.ps1
```

默认端口 **4378**。

## 职责分工（对齐 xa）

| 组件 | 职责 |
|------|------|
| Java | 预建 session/task、转发 SSE、只读查询 |
| `plugins/xw-ingest` | Hook **直连 MySQL**：状态、tool、hit、终稿 |

## 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/sessions` | 新建会话（同时在 Hermes 建 session） |
| POST | `/api/chat/ask` | 提问；默认异步返回 `pending`；`wait:true` 同步等到终稿 |
| GET | `/api/chat/tasks/{taskId}` | 轮询查状态 / 答案 |
| GET | `/api/chat/tasks/{taskId}/stream` | **SSE 实时流**（仅展示，不写库） |
| GET | `/api/chat/tasks/{taskId}/tools` | 工具审计（Hook 入库） |
| GET | `/api/chat/tasks/{taskId}/hits` | 归一化命中；`?hitType=&platform=` |
| GET | `/api/chat/tasks/{taskId}/phases` | 粗阶段计划（目前法案 Skill 会写） |
| GET | `/api/chat/sessions/{id}/messages` | 会话历史 |
| GET | `/api/chat/sessions/{id}/tasks` | 会话内任务列表 |
| GET | `/api/chat/skills` | 四个 Skill 触发词 |

### 提问示例

```json
POST /api/chat/ask
{
  "sessionId": "sess_xxx",
  "message": "研判 H.R.9028 …",
  "skill": "bill-impact-analysis"
}
```

`sessionId` / `skill` 可省略：无 session 则新建；无 skill 则按触发词路由，仍无法判定则由模型自主选择。

Ask 返回 `taskId` 后立刻：

```
GET /api/chat/tasks/{taskId}/stream
```

即可收到类似 Hermes chat 的流式事件。任务结束后可查 `/tools`、`/hits` 与 `answerMarkdown`。

同一 `sessionId` 多轮追问会复用同一个 `hermesSessionId`（Hermes 侧历史）；每一轮提问生成新的 `taskId`。

## Postman

导入 [`postman/hermes-xw-chat.postman_collection.json`](postman/hermes-xw-chat.postman_collection.json)，说明见 [`postman/README.md`](postman/README.md)。

## ID 含义

| ID | 作用 |
|----|------|
| `sessionId` | 业务对话线程 |
| `taskId` | 本轮 Skill 执行（pending → running → done/failed，由 Hook 推进） |
| `hermesSessionId` | 调 Hermes `/api/sessions/{id}/chat/stream` 用；Hook 据此绑定活跃任务 |
