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

## 跨平台约定

- `HERMES_HOME=<repo>/var/hermes`（与 hermes-xa 分离）
- `LIXIAN_ROOT=<repo>`、`LIXIAN_PYTHON=<解释器>`（`config.yaml` MCP 路径用，**禁止写死盘符**）
- Windows：`chat.ps1` / `scripts/*.ps1`
- Ubuntu：`chat.sh` / `scripts/*.sh`（symlink 代替 junction）

## 启动 Hermes（Windows）

```powershell
cd D:\hermes-lixian
.\scripts\init-hermes-runtime.ps1
.\scripts\setup-hermes-venv.ps1
.\chat.ps1 gateway
```

## 启动 Hermes（Ubuntu，可与 hermes-xa 同机）

```bash
cd /opt/hermes-lixian   # 或你的 clone 路径
bash scripts/init-hermes-runtime.sh
bash scripts/setup-hermes-venv.sh

# 同机已有 xa 占用 8642 时：改 .env 中 API_SERVER_PORT=8643，
# 并改 clients/lixian-chat/.../application.yml 的 hermes.base-url 端口

chmod +x chat.sh scripts/*.sh
./chat.sh gateway
```

systemd 模板见 `deploy/ubuntu/`。

确保 `.env` 中 `ES_HOST` / `ES_USERNAME` / `ES_PASSWORD` 可用，且 `API_SERVER_ENABLED=true`。

## 启动 Java 流式问答

见 [`clients/lixian-chat/README.md`](clients/lixian-chat/README.md)。
