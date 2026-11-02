# hermes-lixian

从 `hermes-xw` 精简复制的**离线人员 + 组织查询**发行目录。

## 包含内容

| 组件 | 路径 | 说明 |
|------|------|------|
| 人员 MCP | `mcp/servers/identity-mcp-server` | 涉华/台/港人员检索 |
| 组织 MCP | `mcp/servers/org-mcp-server` | 组织三级标签检索 / 入库打标 |
| 人员 Skill | `skills/research/person-relation-tag-query` | |
| 组织 Skill | `skills/research/org-relation-query` | |
| Hermes 运行时 | `hermes-agent` + `var/hermes` | 与 xw 同级用法 |

**已去掉**：电商 MCP、社交媒体 MCP、其它 research skills、采集缓存等。

## 索引

- 人员：`dw_identity_info_lk_country_wise_new_all`
- 组织：`dw_org_info_lk_company`

## 启动

```powershell
cd D:\hermes-lixian
# 首次可初始化运行时
# .\scripts\init-hermes-runtime.ps1
.\chat.ps1
```

确保 `.env` 中 `ES_HOST` / `ES_USERNAME` / `ES_PASSWORD` 可用。

`config.yaml` 与 `mcp/mcp_servers.yaml` 仅注册 `identity-mcp`、`org-mcp`，路径指向本目录。
