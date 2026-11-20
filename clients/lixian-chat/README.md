# lixian-chat

hermes-lixian 的 Java 流式问答网关（Spring Boot 2.6 / JDK8）。

- 对外：**无登录 Token**
- 本阶段：**不落库**（session/task 仅内存）
- 消息：**通用透传**给 Hermes（后续再按语义挂 skill）

## 依赖

1. 用**本仓库**启动 Hermes API Server（不要用 hermes-xa）：
   - Windows：`.\scripts\setup-hermes-venv.ps1` → `.\chat.ps1 gateway`
   - Ubuntu：`bash scripts/setup-hermes-venv.sh` → `./chat.sh gateway`
   （`.env` 中 `API_SERVER_ENABLED=true`；单机默认 `127.0.0.1:8642`，与 xa 同机请改 `8643`）
2. `application.yml` 中 `hermes.api-key` 与 `.env` 的 `API_SERVER_KEY` 一致；`hermes.base-url` 端口与 `API_SERVER_PORT` 一致

## 启动

```bash
cd clients/lixian-chat
mvn -DskipTests spring-boot:run
```

默认端口：`8088`

## 接口

### 1. 创建会话

`POST /api/chat/sessions`

```json
{ "title": "可选" }
```

返回：`sessionId`、`hermesSessionId`

### 2. 提问

`POST /api/chat/ask`

```json
{
  "sessionId": "上一步的 sessionId，可省略（省略则自动建会话）",
  "message": "查询美国涉华智库"
}
```

**直接以 SSE 流式返回**（入库后边跑边推，无需再访问 stream 接口）：首个事件 `connected` 携带 `taskId`、`sessionId`，其后为 `status`、`reasoning.delta`、`assistant.delta`、`tool.*`、`stream_end`。客户端断开不会取消任务，任务仍会跑完并写入 ES；如需中止请调用 `/cancel`。
参数校验失败时返回 JSON：`{"ok":false,"message":"..."}`。

任务状态：`running`（进行中）→ `end`（正常结束） / `cancelled`（取消） / `failed`（失败）

### 3. 取消任务

`POST /api/chat/cancel`

```json
{ "taskId": "task_xxx" }
```

或按会话取消所有进行中任务：

```json
{ "sessionId": "sess_xxx" }
```

会断开 Hermes SSE（触发 agent interrupt），任务状态变为 `cancelled`。

### 4. 重新订阅流式输出（断线重连用，ask 本身已是流式）

`GET /api/chat/tasks/{taskId}/stream`

SSE 事件示例：`connected`、`status`、`reasoning.delta`（思考过程，token 流）、`assistant.delta`（最终回答正文）、`tool.started`、`tool.completed`、`cancelled`、`error`、`stream_end`

### 5. 查询任务快照

`GET /api/chat/tasks/{taskId}`

## 快速联调（PowerShell）

```powershell
# 建会话
$s = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8088/api/chat/sessions -ContentType 'application/json' -Body '{}'
$s

# 提问（直接流式返回；-N 关闭缓冲）
$body = (@{ sessionId = $s.sessionId; message = '你好，简单介绍你能做什么' } | ConvertTo-Json -Compress)
[IO.File]::WriteAllText("$env:TEMP\ask.json", $body, (New-Object Text.UTF8Encoding($false)))
curl.exe -N -X POST http://127.0.0.1:8088/api/chat/ask -H "Content-Type: application/json" --data-binary "@$env:TEMP\ask.json"
```

## 说明

- 前端只对接本服务；不要把 Hermes `:8642` 暴露给浏览器。
- Java → Hermes 仍使用 `hermes.api-key`（服务间密钥，不是用户登录）。
- 重启进程后内存中的 session/task 会丢失（符合本阶段范围）。
