# Hermes 运行时文件说明

Hermes 把**配置 + 运行时状态**都放在 `HERMES_HOME` 下。以前 `chat.ps1` 设的是仓库根目录 `D:\hermes-lixian`，所以 `gateway.lock`、`kanban.db` 等会落在根目录。

现已改为：**`HERMES_HOME=D:\hermes-lixian\var\hermes`**（见 `chat.ps1` + `scripts/init-hermes-runtime.ps1`）。

## 根目录常见文件是否有用

| 文件/目录 | 用途 | 能否删 |
|-----------|------|--------|
| `gateway.pid` | 当前 Gateway 进程 PID | Gateway **已停** 时可删；运行中勿删 |
| `gateway.lock` | Gateway 启动互斥锁 | 停服后可删；若锁残留导致无法启动再删 |
| `gateway_state.json` | 运行状态（running/draining、平台连接） | 停服后可删；运行中由进程写入 |
| `state.db` (+ `-shm`/`-wal`) | 会话与消息历史（Hermes 核心） | 删 = **清空所有 chat 历史** |
| `response_store.db` (+ `-shm`/`-wal`) | API `/v1/responses` 链式上下文 | 删 = 丢失 Responses API 历史 |
| `kanban.db` (+ `*.lock`) | Kanban / deep-plan 任务板 | 删 = 丢失看板任务 |
| `kanban/` | 多 board 时的子目录 | 同上 |
| `verification_evidence.db` | 验证/证据记录 | 一般可删（会丢验证缓存） |
| `channel_directory.json` | 通道目录缓存 | 可删，会重建 |

**结论：** 不是“没用”，而是**运行时数据**。只有 Gateway 停掉后的 `gateway.*` 锁/状态文件可以当垃圾清；`.db` 删之前要想清楚是否要保留历史。

## 以后文件放哪

- 运行时：`var/hermes/`（已加入 `.gitignore`）
- 仓库根保留：`config.yaml`、`skills/`、`.env`、文档、Java 客户端等
- 首次或换机：执行 `.\scripts\init-hermes-runtime.ps1`，再 `.\chat.ps1 chat` / `gateway`

## 清理旧根目录残留（Gateway 已停）

```powershell
# 确认 8642 / hermes gateway 没在跑后再执行
Remove-Item -Force -ErrorAction SilentlyContinue `
  D:\hermes-lixian\gateway.pid, `
  D:\hermes-lixian\gateway.lock, `
  D:\hermes-lixian\gateway_state.json, `
  D:\hermes-lixian\kanban.db.dispatch.lock, `
  D:\hermes-lixian\kanban.db.init.lock
# 若要彻底重置 Hermes 数据（会丢历史）再删 *.db
```

## 说明

Hermes **没有**单独的 `HERMES_RUNTIME_DIR`：除 `HERMES_GATEWAY_LOCK_DIR`（机器级锁，一般在 `%LOCALAPPDATA%`）外，其余默认都在 `HERMES_HOME` 根下。因此用独立子目录 `var/hermes` 作为 `HERMES_HOME` 是官方模型下最干净的做法。
