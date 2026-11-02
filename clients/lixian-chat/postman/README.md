# Postman 流式接口用例

文件：`lixian-chat.postman_collection.json`

## 导入

1. 打开 Postman → **Import** → 选择本 JSON  
2. Collection Variables 中确认 `baseUrl=http://127.0.0.1:8088`

## 前置

1. 本仓库 Hermes gateway 已启动：`.\chat.ps1 gateway`（`HERMES_HOME=var\hermes`，勿用 xa）  
2. Java：`mvn -DskipTests spring-boot:run`（端口 8088）

## 推荐执行顺序

1. **创建会话** → 自动写入 `sessionId`  
2. **提问 ask（带 sessionId）** → 自动写入 `taskId`  
3. **订阅流式** → 立刻 Send（看 Body 里 `event:` / `data:`）  
4. **查询任务** → 看 `status` / `answer`  
5. 可选：**取消任务 cancel**（`taskId` 或 `sessionId`）打断进行中的问答

可选：

- `提问 ask（组织查询）`  
- `提问 ask（不传 sessionId）`  
- `多轮-第二问`（同一 `sessionId`）

## SSE 说明

关注两类流式事件：

- `reasoning.delta`：思考/规划过程（token 级）
- `assistant.delta`：最终回答正文（token 级）

Postman 对 SSE 支持一般：可能等连接结束后才显示全文。  
若看不到增量，可用：

```powershell
curl.exe -N "http://127.0.0.1:8088/api/chat/tasks/<taskId>/stream"
```

Settings → General → **Request timeout** 建议调大（如 0 或 1800000 ms）。

改完 Hermes `api_server` 后需**重启 Hermes gateway** 才生效。
