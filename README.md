# hermes-lixian

离线**人员 + 组织**自然语言查询发行目录。

## 包含内容

| 组件 | 路径 | 说明 |
|------|------|------|
| 人员 MCP | `mcp/servers/identity-mcp-server` | 涉华/台/港等人员检索 |
| 组织 MCP | `mcp/servers/org-mcp-server` | 组织三级标签检索 / 入库打标 |
| 查询 Skills | `skills/research/person-query-*`、`org-query-*` | Agent 编排 |
| Hermes 运行时 | `hermes-agent` + `var/hermes` | Agent + API Server |
| Java 流式网关 | `clients/lixian-chat` | sessionId/taskId + SSE（本阶段不落库） |

## 索引

- 人员：`dw_identity_info_lk_country_wise_new_all`
- 组织：`dw_org_info_lk_company`

## 启动 Hermes（本仓库独立运行，不依赖 hermes-xa）

```powershell
cd D:\hermes-lixian

# 1) 首次：初始化运行时目录 + 本仓库 venv（只做一次）
.\scripts\init-hermes-runtime.ps1
.\scripts\setup-hermes-venv.ps1

# 2) 确认没有其它进程占用 8642（尤其不要再开 hermes-xa 的 gateway）

# 3) 启动本仓库 gateway（代码来自 hermes-agent\venv 可编辑安装）
.\chat.ps1 gateway
```

`chat.ps1` 会强制 `HERMES_HOME=D:\hermes-lixian\var\hermes`，并优先使用  
`hermes-agent\venv\Scripts\hermes.exe`（不再默认跳到 xa）。

确保 `.env` 中 `ES_HOST` / `ES_USERNAME` / `ES_PASSWORD` 可用，且 `API_SERVER_ENABLED=true`。

`config.yaml` 与 `mcp/mcp_servers.yaml` 仅注册 `identity-mcp`、`org-mcp`。

## 启动 Java 流式问答

见 [`clients/lixian-chat/README.md`](clients/lixian-chat/README.md)。
