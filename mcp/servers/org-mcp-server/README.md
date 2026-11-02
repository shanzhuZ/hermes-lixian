# 组织 MCP（org-mcp）

索引：`dw_org_info_lk_company`（约 49.7 万组织）

## 工具

| 工具 | 作用 |
|------|------|
| `list_org_types` | 一级类型、二级类型 top、业务标签 top |
| `lookup_org_by_name` | 按名称查（返回 L2 / biz_tags） |
| `lookup_org_by_id` | 按 org_id 查 |
| `search_orgs` | 类型/L2/`biz_tag`/国家/行业/议题/二次筛选 |
| `org_cluster_health` | 健康检查 |

## 启动

```powershell
cd d:\hermes-lixian\mcp\servers\org-mcp-server
py -3 run_org_mcp.py
```

已在 `config.yaml` / `mcp/mcp_servers.yaml` 注册为 `org-mcp`。重启 Hermes 后生效。

## 入库（含规则三级标签）

见 `ingest_orgs.py` / `org_mapping.py` / `org_rule_tagger.py`。

入库时按规则自动写入：
- `org_types` / `org_type_primary` 一级类型（来自文件名）
- `org_type_l2` 二级类型
- `biz_tags` 业务标签（涉华/涉台/半导体…）
- `tag_method=rule_v1`

```powershell
cd d:\hermes-lixian\mcp\servers\org-mcp-server
py -3 ingest_orgs.py --recreate
```

## 三级标签打标（大数据 DeepSeek，可选精标）

调用内网 `http://172.200.200.4:7000/v1` 模型 `dsv4-dspark`，可覆盖规则结果：

- `org_type_l2` 二级类型
- `biz_tags` 业务标签（涉华/涉台/半导体…）

```powershell
cd d:\hermes-lixian\mcp\servers\org-mcp-server

# 试跑 5 条（不写文件）
py -3 tag_orgs_deepseek.py --org-type 智库 --limit 5 --dry-run

# 正式写出 JSONL
py -3 tag_orgs_deepseek.py --org-type 智库 --limit 100 --out tagged_智库.jsonl

# 断点续跑
py -3 tag_orgs_deepseek.py --org-type 智库 --limit 500 --out tagged_智库.jsonl --resume

# 回写 ES（先补 mapping）
py -3 tag_orgs_deepseek.py --ensure-mapping --from-jsonl tagged_智库.jsonl --update-es
```

词表见 `org_taxonomy.py`。环境变量：`ORG_TAG_BASE_URL` / `ORG_TAG_MODEL` / `ORG_TAG_API_KEY`。


## V1 边界

- 有：类型、地理、名称/行业、议题（入库规则 `biz_tags` + 查询弱推导）、多轮筛选指引、人员库按公司名衔接  
- 无：组织关系边、事件库、模型级精标全覆盖、完整组织画像中的资金/合作网络
