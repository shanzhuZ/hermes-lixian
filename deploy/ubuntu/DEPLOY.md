# hermes-lixian 服务器部署步骤（与 xa / hq / hq-test 隔离）

目标机已有：

- `/opt/hermes-xa`
- `/opt/hermes-hq`
- `/opt/hermes-hq-test`

本环境固定安装到 **`/opt/hermes-lixian`**，使用独立 `HERMES_HOME`、独立 Python venv、独立 systemd 服务名、独立 Gateway 端口 **`8645`**，不要改动上述三个目录及其服务。

---

## 0. 隔离原则（部署前先确认）

| 项 | hermes-lixian | 说明 |
|----|---------------|------|
| 代码目录 | `/opt/hermes-lixian` | 不要放进 xa/hq 目录 |
| 运行时 | `/opt/hermes-lixian/var/hermes` | `HERMES_HOME`，锁文件/日志/配置副本都在这里 |
| Python | `/opt/hermes-lixian/hermes-agent/venv` | 本仓库自建 venv，不复用 xa/hq 的解释器 |
| Gateway 端口 | **8645** | 避开 8642 及 xa/hq 已用端口 |
| systemd | `hermes-lixian-gateway` / `lixian-chat` | 服务名带 lixian，勿覆盖其它 unit |
| API Key | 本环境单独生成 | 不要与 xa/hq 共用 |

部署前在服务器执行（只读检查，不要 stop 别人的服务）：

```bash
# 看现有服务与端口，确认 8645 / 你准备给 Java 的端口未被占用
systemctl list-units --type=service --all | grep -E 'hermes|lixian' || true
ss -lntp | grep -E '8642|8643|8644|8645|8088|8089' || true
ls -ld /opt/hermes-xa /opt/hermes-hq /opt/hermes-hq-test
```

若 `8088` 已被占用，Java 改用例如 `8089`（下文有说明）。

---

## 1. 前置依赖

```bash
# Python >= 3.10（建议 3.11）、JDK 8、Maven、git
python3 --version
java -version
mvn -version
git --version
```

确保服务器能访问：

- 模型：`http://172.200.200.1:8004/v1`（以仓库 `config.yaml` 为准）
- ES：与 `.env` / `application.yml` 中配置一致

---

## 2. 放置代码

任选其一（**不要**往 hermes-xa / hq 里合并）：

```bash
# 方式 A：git clone
sudo mkdir -p /opt/hermes-lixian
sudo chown "$USER":"$USER" /opt/hermes-lixian
git clone <你的仓库地址> /opt/hermes-lixian
cd /opt/hermes-lixian
# 按需切分支，例如：git checkout ubantu-deploy

# 方式 B：本机打包上传后解压到 /opt/hermes-lixian
```

```bash
cd /opt/hermes-lixian
chmod +x chat.sh scripts/*.sh
```

---

## 3. 配置本环境（关键：端口 8645）

### 3.1 根目录 `.env`

```bash
cd /opt/hermes-lixian
cp -n .env.example .env
# 若已有本地 .env，上传后务必改端口与密钥
vi .env
```

至少确认：

```bash
ES_HOST=...
ES_USERNAME=...
ES_PASSWORD=...
IDENTITY_INDEX=dw_identity_info_lk_country_wise_new_all
ORG_INDEX=dw_org_info_lk_company

API_SERVER_ENABLED=true
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8645
API_SERVER_KEY=<为本环境单独生成的长随机串>
```

说明：

- `API_SERVER_HOST=127.0.0.1`：Gateway 只本机可访问，由 Java 转发；不要对公网开放 8645。
- `chat.sh` 启动时会把根目录 `.env` / `config.yaml` / `SOUL.md` 同步到 `var/hermes/`。

### 3.2 Java 指向 8645

编辑 `clients/lixian-chat/src/main/resources/application.yml`（或生产用外部配置覆盖）：

```yaml
hermes:
  base-url: http://127.0.0.1:8645
  api-key: <与上面 API_SERVER_KEY 完全一致>
```

若 `8088` 冲突，同时改：

```yaml
server:
  port: 8089
```

并核对 `es.*` 是否指向正确集群（勿误连其它环境专用库，除非业务要求共用索引）。

### 3.3 模型与 MCP

`config.yaml` 一般可直接用仓库版本（MCP 用 `${LIXIAN_ROOT}` / `${LIXIAN_PYTHON}`，不会写死 Windows 盘符）。确认模型地址在服务器网络可达：

```bash
curl -sS -m 5 http://172.200.200.1:8004/v1/models || echo "模型不通，先排查网络"
```

---

## 4. 初始化运行时 + 独立 venv

```bash
cd /opt/hermes-lixian
bash scripts/init-hermes-runtime.sh
bash scripts/setup-hermes-venv.sh
```

检查：

```bash
# HERMES_HOME 必须是本仓库 var/hermes
ls -la /opt/hermes-lixian/var/hermes
readlink -f /opt/hermes-lixian/var/hermes/skills   # 应指向 /opt/hermes-lixian/skills

# hermes 来自本仓库 venv，不是 /opt/hermes-xa/...
/opt/hermes-lixian/hermes-agent/venv/bin/hermes --version
which hermes || true   # 即使 PATH 上有别的 hermes，也要用 ./chat.sh（优先本仓库 venv）
```

---

## 5. 手动试跑（先不要装 systemd）

```bash
cd /opt/hermes-lixian
./chat.sh gateway
```

另开终端：

```bash
ss -lntp | grep 8645
curl -sS http://127.0.0.1:8645/health
# 期望含 hermes-agent / ok 一类信息
```

确认 **没有** 误绑到 8642，且 xa/hq 的端口与进程仍在。

停掉试跑：`Ctrl+C`（或杀本仓库对应进程）。不要 `systemctl stop` 其它 hermes 服务。

Java 试跑：

```bash
cd /opt/hermes-lixian/clients/lixian-chat
# 生产建议先打包
mvn -DskipTests package
java -jar target/lixian-chat-*.jar
# 或开发：mvn -DskipTests spring-boot:run
```

```bash
curl -sS http://127.0.0.1:8088/api/chat/query-tags | head
# 若改了 Java 端口，把 8088 换成实际端口
```

---

## 6. 安装 systemd（与现有三个实例并列）

```bash
sudo cp /opt/hermes-lixian/deploy/ubuntu/hermes-lixian-gateway.service /etc/systemd/system/
sudo cp /opt/hermes-lixian/deploy/ubuntu/lixian-chat.service /etc/systemd/system/
```

如需生产用 jar 启动，编辑 `lixian-chat.service` 的 `ExecStart`，例如：

```ini
ExecStart=/usr/bin/java -jar /opt/hermes-lixian/clients/lixian-chat/target/lixian-chat-0.0.1-SNAPSHOT.jar
```

（以 `target/` 下实际 jar 名为准；可用 `--hermes.base-url=http://127.0.0.1:8645` 覆盖。）

```bash
sudo systemctl daemon-reload
sudo systemctl enable hermes-lixian-gateway lixian-chat
sudo systemctl start hermes-lixian-gateway
sleep 3
sudo systemctl start lixian-chat
sudo systemctl status hermes-lixian-gateway lixian-chat --no-pager
```

日志：

```bash
journalctl -u hermes-lixian-gateway -f
journalctl -u lixian-chat -f
# Hermes 文件日志（本环境）
tail -f /opt/hermes-lixian/var/hermes/logs/gateway.log
```

---

## 7. 验收清单

```bash
# 1) 端口隔离
ss -lntp | grep -E '8645|8088|8089'

# 2) 健康检查
curl -sS http://127.0.0.1:8645/health

# 3) 标签接口
curl -sS http://127.0.0.1:8088/api/chat/query-tags

# 4) 问答（SSE，可 Ctrl+C 打断）
curl -N -X POST http://127.0.0.1:8088/api/chat/ask \
  -H 'Content-Type: application/json' \
  -d '{"message":"查询美国涉华智库"}'

# 5) 确认其它实例未被改动
systemctl is-active <xa/hq 对应服务名> || true
ls /opt/hermes-xa /opt/hermes-hq /opt/hermes-hq-test >/dev/null
```

---

## 8. 日常运维

```bash
# 重启本环境（不影响 xa/hq）
sudo systemctl restart hermes-lixian-gateway
sudo systemctl restart lixian-chat

# 更新代码后
cd /opt/hermes-lixian
git pull
bash scripts/init-hermes-runtime.sh   # 同步 skills 软链等
# 若 hermes-agent 依赖有变：bash scripts/setup-hermes-venv.sh
cd clients/lixian-chat && mvn -DskipTests package
sudo systemctl restart hermes-lixian-gateway lixian-chat
```

禁止事项：

- 不要把本环境的 `HERMES_HOME` 指到 `/opt/hermes-xa/...`
- 不要把 `API_SERVER_PORT` 改回 8642（除非确认空闲且你有意共用，不推荐）
- 不要用 xa/hq 的 venv 跑本仓库 MCP
- 不要对公网直接暴露 8645

---

## 9. 回滚 / 卸载本环境

```bash
sudo systemctl disable --now hermes-lixian-gateway lixian-chat
sudo rm -f /etc/systemd/system/hermes-lixian-gateway.service
sudo rm -f /etc/systemd/system/lixian-chat.service
sudo systemctl daemon-reload
# 仅删除本目录；不要动 xa/hq
# sudo rm -rf /opt/hermes-lixian
```
